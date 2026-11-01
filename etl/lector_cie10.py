"""Lector del catálogo CIE-10 (XLS, XLSX o CSV). Carpeta: etl/ — Sprint 2, Fase 3 (extracción).

Entidad: cie10 (schema.sql). Solo COD_4 es clave de relación; COD_3 y las descripciones son informativas.

es_odontologico: el hospital marca los códigos odontológicos con FORMATO en el Excel (subrayado o relleno de color),
no con una columna. El formato se lee celda por celda. La marca puesta en la fila donde empieza una categoría (la que
trae COD_3) vale para TODA la categoría (K02 completa); la marca en una fila sin COD_3 vale solo para ese código
(S005). Con herencia_categoria=False solo cuentan las filas marcadas. Un CSV no conserva formato: exige una columna
ES_ODONTOLOGICO (SI/NO), que si existe en cualquier formato tiene prioridad sobre el formato.
"""

import re
from dataclasses import dataclass, field

from etl.archivos import FuncionFormato, leer_tabla, texto
from etl.comunes import ErrorFormato, Rechazo
from etl.normalizar import clave_texto, limpiar_codigo_cie10, vacio

_CODIGO = re.compile(r"^[A-Z]\d{2}[0-9A-Z]?$")
_DESCRIPCION = re.compile(r"^DES\w*CION")  # el archivo oficial trae "DESRIPCION" (sin C) en una columna
_SI = {"SI", "S", "1", "TRUE", "VERDADERO", "X"}
_NO = {"", "NO", "N", "0", "FALSE", "FALSO"}
_MAX_FILAS_ENCABEZADO = 15


@dataclass(frozen=True)
class FilaCie10:
    cod_4: str
    descripcion_4: str
    cod_3: str | None
    descripcion_3: str | None
    es_odontologico: bool


@dataclass
class LecturaCie10:
    filas: list[FilaCie10] = field(default_factory=list)
    rechazos: list[Rechazo] = field(default_factory=list)


def _encabezado(celda) -> str:
    return re.sub(r"[_\-]", " ", clave_texto(celda)) if not vacio(celda) else ""


def _ubicar_columnas(fila) -> dict[str, int] | None:
    """Mapa campo -> índice de columna, o None si la fila no es el encabezado del catálogo."""
    claves = [_encabezado(c) for c in fila]
    c4 = next((i for i, c in enumerate(claves) if re.match(r"^COD ?4\b", c)), None)
    descripciones = [i for i, c in enumerate(claves) if _DESCRIPCION.match(c)]
    if c4 is None or not descripciones:
        return None
    c3 = next((i for i, c in enumerate(claves) if re.match(r"^COD ?3\b", c)), None)
    odonto = next((i for i, c in enumerate(claves) if c.replace(" ", "").startswith("ESODONTOLOGICO")), None)
    columnas = {"cod_4": c4}
    if c3 is not None:
        columnas["cod_3"] = c3
    if odonto is not None:
        columnas["odonto"] = odonto
    if len(descripciones) == 1:
        columnas["desc_4"] = descripciones[0]
    else:
        # Cada descripción corresponde al código que aparece en su mismo orden en el archivo.
        codigos = sorted((i, nombre) for i, nombre in ((c4, "4"), (c3, "3")) if i is not None)
        for (_, nombre), indice in zip(codigos, descripciones, strict=False):
            columnas["desc_" + nombre] = indice
    return columnas if "desc_4" in columnas else None


def _valor(fila, columnas: dict[str, int], campo: str):
    i = columnas.get(campo)
    return fila[i] if i is not None and i < len(fila) else None


def _fila_marcada(formato: FuncionFormato, i: int, columnas: dict[str, int]) -> bool:
    """La fila está marcada si alguna de sus celdas de código o descripción lleva subrayado o relleno."""
    campos = ("cod_3", "desc_3", "cod_4", "desc_4")
    return any(formato(i, columnas[c]).marcada for c in campos if c in columnas)


def _crudo(encabezado, fila) -> dict:
    return {f"{j + 1}:{texto(h)}": texto(v) for j, (h, v) in enumerate(zip(encabezado, fila, strict=False))}


def leer_catalogo(ruta, herencia_categoria: bool = True) -> LecturaCie10:
    filas, formato = leer_tabla(ruta, con_formato=True)
    indice_encabezado, columnas = None, None
    for i, fila in enumerate(filas[:_MAX_FILAS_ENCABEZADO]):
        columnas = _ubicar_columnas(fila)
        if columnas:
            indice_encabezado = i
            break
    if columnas is None or indice_encabezado is None:
        raise ErrorFormato(
            f"No se encontró el encabezado del catálogo en las primeras {_MAX_FILAS_ENCABEZADO} filas. "
            "Se esperan las columnas COD_4 y DESCRIPCION (y opcionalmente COD_3 y ES_ODONTOLOGICO)."
        )

    por_formato = "odonto" not in columnas
    if por_formato and formato is None:
        raise ErrorFormato(
            "Un CSV no conserva el subrayado ni el color que marcan los códigos odontológicos. "
            "Agregue una columna ES_ODONTOLOGICO con SI o NO, o cargue el catálogo en Excel (XLS o XLSX)."
        )

    encabezado = filas[indice_encabezado]
    lectura = LecturaCie10()
    vistos: set[str] = set()
    categoria = {"cod_3": None, "descripcion_3": None, "marcada": False}  # categoría (COD_3) en curso
    for i in range(indice_encabezado + 1, len(filas)):
        fila = filas[i]
        if all(vacio(v) for v in fila):
            continue
        numero = i + 1

        def rechazar(motivo: str, numero=numero, fila=fila) -> None:
            lectura.rechazos.append(Rechazo(numero, motivo, _crudo(encabezado, fila)))

        marcada = por_formato and _fila_marcada(formato, i, columnas)
        cod_3_bruto = _valor(fila, columnas, "cod_3")
        if not vacio(cod_3_bruto):  # empieza una categoría nueva
            categoria = {
                "cod_3": limpiar_codigo_cie10(texto(cod_3_bruto)),
                "descripcion_3": texto(_valor(fila, columnas, "desc_3")) or None,
                "marcada": marcada,
            }

        bruto = _valor(fila, columnas, "cod_4")
        if vacio(bruto):
            rechazar("Fila sin COD_4")
            continue
        cod_4 = limpiar_codigo_cie10(texto(bruto))
        if not _CODIGO.match(cod_4):
            rechazar(f"COD_4 con formato inválido: {texto(bruto)!r}")
            continue
        descripcion_4 = texto(_valor(fila, columnas, "desc_4"))
        if not descripcion_4 and cod_4 == categoria["cod_3"]:  # categoría sin subdivisión (G14): su única descripción
            descripcion_4 = texto(_valor(fila, columnas, "desc_3"))
        if not descripcion_4:
            rechazar(f"El código {cod_4} no tiene descripción")
            continue
        if cod_4 in vistos:
            rechazar(f"COD_4 {cod_4} repetido en el archivo: se conserva la primera aparición")
            continue

        if por_formato:
            es_odontologico = marcada or (
                herencia_categoria and categoria["marcada"] and _en_categoria(cod_4, categoria)
            )
        else:
            marca = clave_texto(texto(_valor(fila, columnas, "odonto")))
            if marca not in _SI | _NO:
                rechazar(f"ES_ODONTOLOGICO debe ser SI o NO, no {marca!r}")
                continue
            es_odontologico = marca in _SI

        if _en_categoria(cod_4, categoria):
            cod_3, descripcion_3 = categoria["cod_3"], categoria["descripcion_3"]
        else:
            cod_3, descripcion_3 = cod_4[:3], None
        descripcion_3 = texto(_valor(fila, columnas, "desc_3")) or descripcion_3
        vistos.add(cod_4)
        lectura.filas.append(FilaCie10(cod_4, descripcion_4, cod_3, descripcion_3, bool(es_odontologico)))

    if not lectura.filas:
        raise ErrorFormato("El archivo no contiene ningún código CIE-10 válido.")
    if por_formato and not any(f.es_odontologico for f in lectura.filas):
        raise ErrorFormato(
            "No se encontró ninguna celda subrayada ni resaltada con color, así que ningún código quedaría marcado "
            "como odontológico. Verifique el formato en las celdas COD_4 o su descripción."
        )
    return lectura


def _en_categoria(cod_4: str, categoria: dict) -> bool:
    return bool(categoria["cod_3"]) and cod_4.startswith(categoria["cod_3"])
