"""Errores de dominio. Los routers los traducen a HTTP. Carpeta: app/services."""


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass
