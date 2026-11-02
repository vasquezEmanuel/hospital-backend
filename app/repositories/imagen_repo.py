"""Acceso a datos de imagen_clinica. Carpeta: app/repositories — Sprint 3.

Entidad imagen_clinica. Regla 4 (toda imagen pertenece, como mínimo, a un paciente), regla 5 (solo imágenes activas:
nunca DELETE físico) y regla 7 (aquí solo viven las claves del almacenamiento; el enlace firmado lo arma el servicio).
"""

import re
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, aliased

from app.models import Atencion, DiagnosticoBucal, ImagenClinica, Paciente
from app.models.diagnostico import cie10_x_diagnostico_bucal as puente
from app.repositories.busqueda import normalizar_busqueda, sin_tildes

COLOMBIA = timezone(timedelta(hours=-5))  # sin horario de verano: evita depender de la base de zonas horarias del SO
_DOC_SEPARATORS = re.compile(r"[.\s-]")

# (imagen, nombre del paciente, fecha de la atención o None, texto del diagnóstico bucal o None)
FilaImagen = tuple[ImagenClinica, str, date | None, str | None]


def _base() -> Select:
    return (
        select(ImagenClinica, Paciente.nombre, Atencion.fecha_atencion, DiagnosticoBucal.descripcion)
        .join(Paciente, Paciente.id_paciente == ImagenClinica.id_paciente)
        .outerjoin(Atencion, Atencion.id_atencion == ImagenClinica.id_atencion)
        .outerjoin(DiagnosticoBucal, DiagnosticoBucal.id_diagnostico_bucal == ImagenClinica.id_diagnostico_bucal)
        .where(ImagenClinica.activo.is_(True))  # regla 5: las inactivas no se muestran
    )


def listar(
    db: Session,
    *,
    id_paciente: int | None,
    id_atencion: int | None,
    q: str | None,
    cod_4: str | None,
    fecha_desde: date | None,
    fecha_hasta: date | None,
    page: int,
    page_size: int,
) -> tuple[list[FilaImagen], int]:
    base = _base()
    if id_paciente is not None:
        base = base.where(ImagenClinica.id_paciente == id_paciente)
    if id_atencion is not None:
        base = base.where(ImagenClinica.id_atencion == id_atencion)
    if q:
        q = q.strip()
        condiciones = [sin_tildes(Paciente.nombre).contains(normalizar_busqueda(q), autoescape=True)]
        solo_doc = _DOC_SEPARATORS.sub("", q)
        if solo_doc:
            condiciones.append(Paciente.documento_identidad.icontains(solo_doc, autoescape=True))
        base = base.where(or_(*condiciones))
    if cod_4:
        # Imágenes ligadas a un diagnóstico bucal con ese código, directamente o a través de su atención.
        dx = aliased(DiagnosticoBucal)  # alias: si no, el subselect se "correlaciona" con el join de arriba
        con_codigo = (
            select(dx.id_diagnostico_bucal)
            .join(puente, puente.c.id_diagnostico_bucal == dx.id_diagnostico_bucal)
            .where(
                puente.c.cod_4 == cod_4.strip().upper(),
                dx.activo.is_(True),
                or_(
                    dx.id_diagnostico_bucal == ImagenClinica.id_diagnostico_bucal,
                    dx.id_atencion == ImagenClinica.id_atencion,
                ),
            )
        )
        base = base.where(exists(con_codigo))
    if fecha_desde:  # fecha de carga, en hora de Colombia
        base = base.where(ImagenClinica.fecha_carga >= datetime.combine(fecha_desde, time.min, COLOMBIA))
    if fecha_hasta:
        base = base.where(
            ImagenClinica.fecha_carga < datetime.combine(fecha_hasta + timedelta(days=1), time.min, COLOMBIA)
        )

    total = db.scalar(select(func.count()).select_from(base.order_by(None).subquery())) or 0
    filas = db.execute(
        base.order_by(ImagenClinica.fecha_carga.desc(), ImagenClinica.id_imagen.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()
    return [tuple(f) for f in filas], total


def obtener_fila(db: Session, id_imagen: int) -> FilaImagen | None:
    fila = db.execute(_base().where(ImagenClinica.id_imagen == id_imagen)).first()
    return tuple(fila) if fila else None


def obtener_activa(db: Session, id_imagen: int) -> ImagenClinica | None:
    imagen = db.get(ImagenClinica, id_imagen)
    return imagen if imagen is not None and imagen.activo else None


def por_paciente(db: Session, id_paciente: int) -> list[FilaImagen]:
    filas = db.execute(
        _base()
        .where(ImagenClinica.id_paciente == id_paciente)
        .order_by(ImagenClinica.fecha_carga.desc(), ImagenClinica.id_imagen.desc())
    ).all()
    return [tuple(f) for f in filas]


def existe_checksum(db: Session, id_paciente: int, checksum: str) -> bool:
    return (
        db.scalar(
            select(
                exists().where(
                    ImagenClinica.id_paciente == id_paciente,
                    ImagenClinica.checksum == checksum,
                    ImagenClinica.activo.is_(True),
                )
            )
        )
        or False
    )


def registrar_o_enriquecer(db: Session, valores: dict) -> int:
    """Alta desde la API. Si la función de indexación ya registró esa clave (el evento llegó antes del commit),
    se completan los vínculos (atención, diagnóstico) en vez de fallar. Devuelve id_imagen."""
    tabla = ImagenClinica.__table__
    stmt = pg_insert(tabla).values(**valores)
    stmt = stmt.on_conflict_do_update(
        index_elements=[tabla.c.url_almacenamiento],
        set_={
            campo: stmt.excluded[campo]
            for campo in ("id_atencion", "id_diagnostico_bucal", "nombre_archivo", "metadata", "checksum")
        },
    ).returning(tabla.c.id_imagen)
    return db.execute(stmt).scalar_one()


def registrar_si_falta(db: Session, valores: dict) -> int | None:
    """Alta idempotente desde la función de indexación: si la clave ya existe no hace nada y devuelve None."""
    tabla = ImagenClinica.__table__
    stmt = (
        pg_insert(tabla)
        .values(**valores)
        .on_conflict_do_nothing(index_elements=[tabla.c.url_almacenamiento])
        .returning(tabla.c.id_imagen)
    )
    return db.execute(stmt).scalar_one_or_none()
