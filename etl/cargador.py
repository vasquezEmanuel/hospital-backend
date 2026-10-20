"""Cargador del ETL a PostgreSQL. Carpeta: etl/ — Sprint 2, Fase 3 del documento técnico (carga).

Entidades: cie10, paciente, aseguradora, profesional, atencion, diagnostico_hospitalario, diagnostico_bucal,
cie10_x_diagnostico_bucal, importacion, importacion_fila (schema.sql v1.2).
Reglas del prompt: 1 (documento único), 2 (diagnóstico bucal solo con códigos odontológicos), 3 (a lo sumo un
diagnóstico de hospitalización por atención). Fase 3: lo que no coincide NO se descarta ni se asigna sin respaldo:
la fila completa va a la cola de revisión (importacion_fila) y de ella no se inserta nada.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from etl.comunes import ErrorFormato, Rechazo
from etl.lector_atenciones import FilaAtencion, leer_atenciones
from etl.lector_cie10 import leer_catalogo
from etl.normalizar import clave_texto, limpiar_codigo_cie10

_TOKEN_CODIGO = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]\d{2}\.?[0-9A-Za-z]?)(?![A-Za-z0-9])")
_MAX_EJEMPLOS = 10


@dataclass
class ResultadoCarga:
    tipo: str
    archivo: str
    total: int = 0
    insertados: int = 0
    actualizados: int = 0
    omitidos: int = 0  # ya existían tal cual: no se duplican
    rechazados: int = 0  # van a importacion_fila para revisión manual
    pacientes_nuevos: int = 0
    aseguradoras_nuevas: int = 0
    id_importacion: int | None = None
    ejemplos: list[str] = field(default_factory=list)

    def lineas(self) -> list[str]:
        salida = [
            f"Importación #{self.id_importacion} ({self.tipo}) — archivo: {self.archivo}",
            f"  Registros en el archivo : {self.total}",
            f"  Insertados              : {self.insertados}",
            f"  Actualizados            : {self.actualizados}",
            f"  Omitidos (ya existían)  : {self.omitidos}",
            f"  A revisión manual       : {self.rechazados}",
        ]
        if self.tipo == "atenciones":
            salida += [
                f"  Pacientes nuevos        : {self.pacientes_nuevos}",
                f"  Aseguradoras nuevas     : {self.aseguradoras_nuevas}",
            ]
        if self.ejemplos:
            salida.append("  Motivos de revisión (primeros):")
            salida += [f"    - {e}" for e in self.ejemplos]
        return salida


# ---------------------------------------------------------------- registro de la importación


def _abrir_importacion(db: Session, tipo: str, archivo: str, total: int) -> int:
    id_importacion = db.execute(
        text(
            "INSERT INTO importacion (tipo, nombre_archivo, estado, total_registros) "
            "VALUES (:tipo, :archivo, 'procesando', :total) RETURNING id_importacion"
        ),
        {"tipo": tipo, "archivo": archivo, "total": total},
    ).scalar_one()
    db.commit()  # el registro queda aunque la carga falle después
    return id_importacion


def _cerrar_importacion(db: Session, r: ResultadoCarga, estado: str) -> None:
    db.execute(
        text(
            "UPDATE importacion SET estado = :estado, insertados = :i, actualizados = :a, rechazados = :r, "
            "finalizado_en = now() WHERE id_importacion = :id"
        ),
        {"estado": estado, "i": r.insertados, "a": r.actualizados, "r": r.rechazados, "id": r.id_importacion},
    )


def _guardar_filas(db: Session, id_importacion: int, rechazos: list[Rechazo], estado: str) -> None:
    if not rechazos:
        return
    db.execute(
        text(
            "INSERT INTO importacion_fila (id_importacion, numero_fila, estado, motivo, datos) "
            "VALUES (:imp, :fila, :estado, :motivo, CAST(:datos AS jsonb))"
        ),
        [
            {
                "imp": id_importacion,
                "fila": r.numero_fila,
                "estado": estado,
                "motivo": r.motivo,
                "datos": json.dumps(r.datos, ensure_ascii=False),
            }
            for r in sorted(rechazos, key=lambda x: x.numero_fila)
        ],
    )


def _registrar_rechazos(r: ResultadoCarga, rechazos: list[Rechazo]) -> None:
    r.rechazados = len(rechazos)
    for rechazo in sorted(rechazos, key=lambda x: x.numero_fila)[:_MAX_EJEMPLOS]:
        r.ejemplos.append(f"fila {rechazo.numero_fila}: {rechazo.motivo}")


# ---------------------------------------------------------------- catálogo CIE-10


def cargar_catalogo(db: Session, ruta) -> ResultadoCarga:
    """Inserta los códigos nuevos y actualiza los que cambiaron. Repetir la carga no duplica nada."""
    lectura = leer_catalogo(ruta)  # si el archivo no sirve, falla antes de tocar la base
    resultado = ResultadoCarga("cie10", Path(ruta).name, total=len(lectura.filas) + len(lectura.rechazos))
    resultado.id_importacion = _abrir_importacion(db, "cie10", resultado.archivo, resultado.total)
    try:
        existentes = {
            f.cod_4: (f.cod_3, f.descripcion_3, f.descripcion_4, f.es_odontologico)
            for f in db.execute(
                text("SELECT cod_4, cod_3, descripcion_3, descripcion_4, es_odontologico FROM cie10")
            ).all()
        }
        nuevos, cambiados = [], []
        for f in lectura.filas:
            params = {
                "cod_4": f.cod_4,
                "cod_3": f.cod_3,
                "d3": f.descripcion_3,
                "d4": f.descripcion_4,
                "odonto": f.es_odontologico,
            }
            actual = existentes.get(f.cod_4)
            if actual is None:
                nuevos.append(params)
            elif actual != (f.cod_3, f.descripcion_3, f.descripcion_4, f.es_odontologico):
                cambiados.append(params)
            else:
                resultado.omitidos += 1
        if nuevos:
            db.execute(
                text(
                    "INSERT INTO cie10 (cod_4, cod_3, descripcion_3, descripcion_4, es_odontologico) "
                    "VALUES (:cod_4, :cod_3, :d3, :d4, :odonto)"
                ),
                nuevos,
            )
        if cambiados:
            db.execute(
                text(
                    "UPDATE cie10 SET cod_3 = :cod_3, descripcion_3 = :d3, descripcion_4 = :d4, "
                    "es_odontologico = :odonto WHERE cod_4 = :cod_4"
                ),
                cambiados,
            )
        resultado.insertados, resultado.actualizados = len(nuevos), len(cambiados)
        _guardar_filas(db, resultado.id_importacion, lectura.rechazos, "rechazada")
        _registrar_rechazos(resultado, lectura.rechazos)
        _cerrar_importacion(db, resultado, "completado")
        db.commit()
    except Exception:
        db.rollback()
        _cerrar_importacion(db, resultado, "fallido")
        db.commit()
        raise
    return resultado


# ---------------------------------------------------------------- atenciones


class _FilaEnRevision(Exception):
    def __init__(self, motivos: list[str]):
        super().__init__("; ".join(motivos))
        self.motivos = motivos


@dataclass
class _Catalogo:
    por_codigo: dict[str, bool]  # cod_4 -> es_odontologico
    por_descripcion: dict[str, list[str]]  # clave_texto(descripcion_4) -> [cod_4]


@dataclass
class _Contexto:
    catalogo: _Catalogo
    aseguradoras: dict[str, int]  # clave_texto(nombre) -> id
    profesionales: dict[str, int]
    pacientes_nuevos: int = 0
    aseguradoras_nuevas: int = 0


def _cargar_contexto(db: Session) -> _Contexto:
    por_codigo: dict[str, bool] = {}
    por_descripcion: dict[str, list[str]] = {}
    for cod_4, descripcion, odonto in db.execute(text("SELECT cod_4, descripcion_4, es_odontologico FROM cie10")):
        por_codigo[cod_4] = odonto
        por_descripcion.setdefault(clave_texto(descripcion), []).append(cod_4)
    aseguradoras = {
        clave_texto(n): i for i, n in db.execute(text("SELECT id_aseguradora, nombre FROM aseguradora")).all()
    }
    profesionales = {
        clave_texto(n): i for i, n in db.execute(text("SELECT id_profesional, nombre FROM profesional")).all()
    }
    return _Contexto(_Catalogo(por_codigo, por_descripcion), aseguradoras, profesionales)


def _resolver_codigos(valor: str, cat: _Catalogo) -> tuple[list[str], str | None]:
    """Texto libre de una celda de diagnóstico -> códigos cod_4 del catálogo (o el motivo por el que no se pudo)."""
    # 1) la celda completa es la descripción de un código
    exactos = cat.por_descripcion.get(clave_texto(valor))
    if exactos:
        if len(exactos) == 1:
            return exactos, None
        return [], f"la descripción coincide con varios códigos: {', '.join(exactos)}"
    # 2) la celda trae uno o más códigos ("K021", "K02.1 - Caries...", "K021, K051")
    codigos = list(dict.fromkeys(limpiar_codigo_cie10(m.group(1)) for m in _TOKEN_CODIGO.finditer(valor)))
    if codigos:
        desconocidos = [c for c in codigos if c not in cat.por_codigo]
        if desconocidos:
            return [], f"el código {', '.join(desconocidos)} no existe en el catálogo CIE-10"
        return codigos, None
    # 3) varias descripciones separadas por ; o salto de línea
    piezas = [p.strip() for p in re.split(r"[;\n]", valor) if p.strip()]
    if len(piezas) > 1:
        encontrados = []
        for pieza in piezas:
            coincidencias = cat.por_descripcion.get(clave_texto(pieza))
            if not coincidencias or len(coincidencias) != 1:
                return [], f"sin coincidencia en el catálogo CIE-10: {pieza!r}"
            encontrados.append(coincidencias[0])
        return list(dict.fromkeys(encontrados)), None
    return [], f"sin coincidencia en el catálogo CIE-10: {valor!r}"


def _resolver_diagnosticos(fila: FilaAtencion, cat: _Catalogo) -> tuple[str | None, list[tuple[str, list[str]]]]:
    motivos: list[str] = []
    hospitalario = None
    if fila.dx_hospitalario:
        codigos, error = _resolver_codigos(fila.dx_hospitalario, cat)
        if error:
            motivos.append(f"Diagnóstico de hospitalización: {error}")
        elif len(codigos) != 1:  # regla 3: a lo sumo uno
            motivos.append(f"Diagnóstico de hospitalización: se esperaba 1 código y hay {len(codigos)}")
        else:
            hospitalario = codigos[0]
    bucales: list[tuple[str, list[str]]] = []
    for numero, valor in fila.dx_bucales:
        codigos, error = _resolver_codigos(valor, cat)
        if error:
            motivos.append(f"Diagnóstico bucal {numero}: {error}")
            continue
        no_odontologicos = [c for c in codigos if not cat.por_codigo[c]]
        if no_odontologicos:  # regla 2
            motivos.append(
                f"Diagnóstico bucal {numero}: {', '.join(no_odontologicos)} no está marcado como odontológico"
            )
            continue
        bucales.append((valor, codigos))
    if motivos:
        raise _FilaEnRevision(motivos)
    return hospitalario, bucales


def _procesar_fila(db: Session, fila: FilaAtencion, ctx: _Contexto) -> str:
    """Inserta una fila completa o no inserta nada. Devuelve 'insertado' u 'omitido'."""
    hospitalario, bucales = _resolver_diagnosticos(fila, ctx.catalogo)
    agregadas: list[str] = []
    try:
        with db.begin_nested():  # savepoint: si algo falla, esta fila no deja rastro
            id_paciente = db.execute(
                text("SELECT id_paciente FROM paciente WHERE documento_identidad = :doc"), {"doc": fila.documento}
            ).scalar()
            paciente_nuevo = id_paciente is None
            if paciente_nuevo:  # regla 1: el documento identifica al paciente
                id_paciente = db.execute(
                    text(
                        "INSERT INTO paciente (documento_identidad, nombre) VALUES (:doc, :nombre) "
                        "RETURNING id_paciente"
                    ),
                    {"doc": fila.documento, "nombre": fila.nombre},
                ).scalar_one()
            else:
                existe = db.execute(
                    text(
                        "SELECT 1 FROM atencion WHERE id_paciente = :p AND fecha_atencion = :f "
                        "AND ubicacion IS NOT DISTINCT FROM :u AND plan_tratamiento IS NOT DISTINCT FROM :pl "
                        "AND observaciones IS NOT DISTINCT FROM :o LIMIT 1"
                    ),
                    {"p": id_paciente, "f": fila.fecha, "u": fila.ubicacion, "pl": fila.plan, "o": fila.observaciones},
                ).first()
                if existe:
                    return "omitido"

            id_aseguradora, aseguradora_nueva = None, False
            if fila.aseguradora:
                clave = clave_texto(fila.aseguradora)
                id_aseguradora = ctx.aseguradoras.get(clave)
                if id_aseguradora is None:
                    id_aseguradora = db.execute(
                        text("INSERT INTO aseguradora (nombre) VALUES (:n) RETURNING id_aseguradora"),
                        {"n": fila.aseguradora},
                    ).scalar_one()
                    ctx.aseguradoras[clave] = id_aseguradora
                    agregadas.append(clave)
                    aseguradora_nueva = True

            # profesional_texto es el respaldo: si no hay coincidencia, el dato original se conserva
            id_profesional = ctx.profesionales.get(clave_texto(fila.profesional)) if fila.profesional else None
            profesional_texto = None if id_profesional else fila.profesional

            id_atencion = db.execute(
                text(
                    "INSERT INTO atencion (id_paciente, fecha_atencion, id_aseguradora, ubicacion, id_profesional, "
                    "profesional_texto, plan_tratamiento, observaciones) "
                    "VALUES (:p, :f, :a, :u, :prof, :prof_txt, :pl, :o) RETURNING id_atencion"
                ),
                {
                    "p": id_paciente,
                    "f": fila.fecha,
                    "a": id_aseguradora,
                    "u": fila.ubicacion,
                    "prof": id_profesional,
                    "prof_txt": profesional_texto,
                    "pl": fila.plan,
                    "o": fila.observaciones,
                },
            ).scalar_one()
            if hospitalario:
                db.execute(
                    text(
                        "INSERT INTO diagnostico_hospitalario (id_atencion, descripcion_original, cod_4) "
                        "VALUES (:a, :d, :c)"
                    ),
                    {"a": id_atencion, "d": fila.dx_hospitalario, "c": hospitalario},
                )
            for descripcion, codigos in bucales:
                id_bucal = db.execute(
                    text(
                        "INSERT INTO diagnostico_bucal (id_atencion, descripcion) VALUES (:a, :d) "
                        "RETURNING id_diagnostico_bucal"
                    ),
                    {"a": id_atencion, "d": descripcion},
                ).scalar_one()
                for cod_4 in codigos:
                    db.execute(
                        text("INSERT INTO cie10_x_diagnostico_bucal (cod_4, id_diagnostico_bucal) VALUES (:c, :d)"),
                        {"c": cod_4, "d": id_bucal},
                    )
    except Exception:
        for clave in agregadas:  # la aseguradora creada en este savepoint ya no existe
            ctx.aseguradoras.pop(clave, None)
        raise
    ctx.pacientes_nuevos += paciente_nuevo
    ctx.aseguradoras_nuevas += aseguradora_nueva
    return "insertado"


def cargar_atenciones(db: Session, ruta) -> ResultadoCarga:
    """Carga la hoja de atenciones. Requiere el catálogo CIE-10 cargado. Repetir la carga no duplica atenciones."""
    lectura = leer_atenciones(ruta)
    ctx = _cargar_contexto(db)
    if not ctx.catalogo.por_codigo:
        raise ErrorFormato("El catálogo CIE-10 está vacío: cargue primero el catálogo (comando 'catalogo').")
    resultado = ResultadoCarga("atenciones", Path(ruta).name, total=len(lectura.filas) + len(lectura.rechazos))
    resultado.id_importacion = _abrir_importacion(db, "atenciones", resultado.archivo, resultado.total)
    try:
        revision = list(lectura.rechazos)
        for fila in lectura.filas:
            try:
                estado = _procesar_fila(db, fila, ctx)
            except _FilaEnRevision as exc:
                revision.append(Rechazo(fila.numero_fila, "; ".join(exc.motivos), fila.crudo))
                continue
            except SQLAlchemyError as exc:
                detalle = str(getattr(exc, "orig", exc)).splitlines()[0][:200]
                revision.append(Rechazo(fila.numero_fila, f"Error de base de datos: {detalle}", fila.crudo))
                continue
            if estado == "insertado":
                resultado.insertados += 1
            else:
                resultado.omitidos += 1
        resultado.pacientes_nuevos = ctx.pacientes_nuevos
        resultado.aseguradoras_nuevas = ctx.aseguradoras_nuevas
        _guardar_filas(db, resultado.id_importacion, revision, "revision")
        _registrar_rechazos(resultado, revision)
        _cerrar_importacion(db, resultado, "completado")
        db.commit()
    except Exception:
        db.rollback()
        _cerrar_importacion(db, resultado, "fallido")
        db.commit()
        raise
    return resultado