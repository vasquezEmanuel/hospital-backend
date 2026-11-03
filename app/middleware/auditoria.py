"""Auditoría por solicitud. Carpeta: app/middleware — Sprint 4, regla 6.

No es un middleware global a propósito: para auditar hay que saber QUÉ paciente se consultó y QUIÉN es el usuario, y eso
solo se conoce dentro de cada ruta. Cada ruta que toca datos de pacientes declara
`auditor: Auditor = Depends(get_auditor)` y llama a `auditor.registrar(...)` antes de entregar o modificar el dato.
Una prueba recorre todas las rutas y falla si alguna ruta de datos de pacientes no declara el auditor.

La IP es la del cliente que ve la aplicación. Detrás de un balanceador o API Gateway, el servidor debe arrancar con
`--proxy-headers` y `--forwarded-allow-ips` apuntando al balanceador (configuración de despliegue) para que sea la real.
"""

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.services import auditoria_service


class Auditor:
    def __init__(self, db: Session, user: CurrentUser, ip: str | None):
        self._db, self._user, self._ip = db, user, ip

    def registrar(self, accion: str, entidad: str | None, **kwargs) -> None:
        auditoria_service.registrar(self._db, self._user, self._ip, accion, entidad, **kwargs)


def get_auditor(
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> Auditor:
    return Auditor(db, user, request.client.host if request.client else None)
