# Copias de seguridad

Qué hay que respaldar (son **dos** cosas distintas):

| Qué | Dónde vive | Cómo se respalda |
|---|---|---|
| Base de datos (pacientes, atenciones, diagnósticos, auditoría) | Supabase (PostgreSQL) | Respaldo automático del plan + `scripts/respaldo.sh` |
| Imágenes clínicas (los archivos) | Supabase Storage, bucket `imagenes-clinicas` | Descarga periódica del bucket (ver abajo) |

Un respaldo de la base **sin** las imágenes deja las filas apuntando a archivos que ya no están, y al revés.

## 1. Lo que ofrece Supabase
Entra a Supabase → **Database → Backups** y revisa qué cubre el plan del proyecto (copias diarias automáticas, cuántos días
se conservan, y si hay recuperación a un punto en el tiempo). Los planes cambian: confirma ahí lo vigente. Si el plan no
incluye copias automáticas, el punto 2 es obligatorio.

## 2. Respaldo propio de la base (`scripts/respaldo.sh`)
Requiere `pg_dump` / `pg_restore` (vienen con PostgreSQL 16 client tools) en el computador desde el que se ejecute.

1. Supabase → botón **Connect** → cadena de conexión *Session pooler* (puerto 5432) del usuario **`postgres`** (no `hospital_api`).
2. Ejecutar (Linux/macOS/WSL/Git Bash):
   ```bash
   export RESPALDO_DATABASE_URL='postgresql://postgres.oqqmchuzsqknmgtnfadu:CLAVE@aws-0-us-east-1.pooler.supabase.com:5432/postgres?sslmode=require'
   ./scripts/respaldo.sh ./respaldos
   ```
3. El archivo `.dump` resultante tiene datos de pacientes: guardarlo **fuera del repositorio**, cifrado (disco cifrado o
   un ZIP/7z con clave) y en un lugar distinto al computador de trabajo.

Frecuencia sugerida: **diaria** si hay uso diario; como mínimo **semanal** y siempre antes de una migración o una importación grande.
Conservar al menos los últimos 7 diarios y 4 semanales.

## 3. Respaldo de las imágenes
Supabase → **Storage → imagenes-clinicas**: se puede descargar por carpeta desde el panel. Para automatizarlo, el bucket
es compatible con S3 (Project Settings → Storage → *S3 Connection*) y se puede copiar con cualquier cliente S3
(`aws s3 sync` o `rclone`). Es una herramienta de operación, no parte del código de la app.

## 4. Restaurar (probar al menos una vez ANTES de necesitarlo)
Un respaldo que nunca se probó no es un respaldo. Probar en una base **vacía** (un proyecto Supabase nuevo o un PostgreSQL local), nunca sobre producción:

```bash
pg_restore --no-owner --no-privileges --dbname="URL_DE_LA_BASE_VACIA" archivo.dump
```
Después de restaurar en una base nueva hay que volver a ejecutar `docs/sql/seguridad_bd.sql` (rol `hospital_api`, permisos y
políticas), porque el respaldo se hace con `--no-privileges`. Luego comprobar `GET /health/ready` y que el número de pacientes
coincida con el esperado.

## 5. Lista de verificación mensual
- [ ] El último respaldo tiene menos de 24 h (o la frecuencia acordada).
- [ ] Se restauró uno de prueba en una base vacía y los conteos coinciden.
- [ ] Las imágenes también se respaldaron en la misma fecha.
- [ ] Los respaldos están cifrados y fuera del repositorio.
