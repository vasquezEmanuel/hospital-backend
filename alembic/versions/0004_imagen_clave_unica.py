"""v1.3 — una imagen = una clave de almacenamiento, y corrección de los índices de importacion_fila.

1) La función de indexación se dispara por evento y puede recibir el mismo evento más de una vez (entrega "al menos una
   vez" de los servicios de eventos), o correr a la vez que la carga inicial. El índice único impide imágenes duplicadas
   y permite INSERT ... ON CONFLICT DO NOTHING. Sprint 3, regla 4 (toda imagen queda asociada al paciente).
2) Corrección: la migración 0003 creó idx_importacion_fila_imp e idx_importacion_fila_estado sobre la tabla
   `importacion` en lugar de `importacion_fila`. Se recrean sobre la tabla correcta (cola de revisión del importador).

Revision ID: 0004
Revises: 0003
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE UNIQUE INDEX uq_imagen_clave ON imagen_clinica (url_almacenamiento)")
    op.execute("DROP INDEX idx_importacion_fila_imp")
    op.execute("DROP INDEX idx_importacion_fila_estado")
    op.execute("CREATE INDEX idx_importacion_fila_imp ON importacion_fila (id_importacion)")
    op.execute("CREATE INDEX idx_importacion_fila_estado ON importacion_fila (estado)")


def downgrade() -> None:
    op.execute("DROP INDEX idx_importacion_fila_estado")
    op.execute("DROP INDEX idx_importacion_fila_imp")
    op.execute("CREATE INDEX idx_importacion_fila_imp ON importacion (id_importacion)")
    op.execute("CREATE INDEX idx_importacion_fila_estado ON importacion (estado)")
    op.execute("DROP INDEX uq_imagen_clave")
