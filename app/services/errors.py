"""Errores de dominio. Los routers los traducen a HTTP. Carpeta: app/services."""


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


class DatosInvalidosError(Exception):
    """La solicitud es coherente en forma pero no en contenido (p. ej. una atención de otro paciente) -> 422."""


class ArchivoNoPermitidoError(Exception):
    """El archivo no es una imagen de un formato aceptado -> 415."""


class ArchivoMuyGrandeError(Exception):
    """El archivo supera el máximo permitido -> 413."""
