"""Esquemas Pydantic compartidos. Carpeta: app/schemas."""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Respuesta paginada (el front muestra 'Mostrando 1–5 de 24 resultados')."""

    items: list[T]
    total: int = Field(description="Total de resultados que cumplen el filtro")
    page: int
    page_size: int


class ErrorResponse(BaseModel):
    detail: str
