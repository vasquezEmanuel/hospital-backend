#!/usr/bin/env bash
# Copia de seguridad de la base (esquema public) con pg_dump. Herramienta estándar de PostgreSQL, no del stack de la app.
# Uso:  RESPALDO_DATABASE_URL='postgresql://USUARIO:CLAVE@HOST:5432/postgres?sslmode=require' ./scripts/respaldo.sh [CARPETA]
# La URL (con el usuario propietario `postgres`) se pasa por variable de entorno: NUNCA se guarda en el repositorio.
# Los archivos contienen datos de pacientes: guardarlos cifrados y fuera del repositorio.
set -euo pipefail

: "${RESPALDO_DATABASE_URL:?Falta RESPALDO_DATABASE_URL (ver docs/COPIAS_DE_SEGURIDAD.md)}"
destino="${1:-./respaldos}"
mkdir -p "$destino"
archivo="$destino/hospital_$(date +%Y%m%d_%H%M%S).dump"

pg_dump --format=custom --schema=public --no-owner --no-privileges --file="$archivo" "$RESPALDO_DATABASE_URL"
# Comprobación mínima: el archivo debe poder listarse y no estar vacío.
pg_restore --list "$archivo" > /dev/null
echo "Respaldo listo: $archivo ($(du -h "$archivo" | cut -f1))"
