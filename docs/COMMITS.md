# Estándar de commits

Formato (Conventional Commits, en español):

    tipo(alcance): resumen en minúsculas, sin punto final

    Por qué se hizo (opcional).

    Sprint N · Paso M

El alcance es opcional cuando el tipo ya lo dice (`db:`, `docs:`).

## Tipos
| Tipo | Cuándo |
|---|---|
| feat | Funcionalidad nueva (endpoint, módulo, función) |
| fix | Corrección de un error |
| db | Cambio de esquema: **`schema.sql` + migración Alembic en el mismo commit** |
| test | Solo pruebas |
| docs | Solo documentación |
| refactor | Reorganiza código sin cambiar su comportamiento |
| ci | Workflows de GitHub Actions, Docker |
| chore | Mantenimiento: dependencias, `.gitignore`, configuración |

## Alcances (la carpeta o capa que tocas)
`db` · `api` (routers, services, repositories, schemas) · `auth` · `etl` · `imagenes` · `funciones` · `docs` · `ci`

## Reglas
1. Un commit = un cambio con un solo propósito. Si necesitas escribir "y" en el resumen, son dos commits.
2. Resumen en imperativo y de máximo 72 caracteres: `agrega`, `corrige`, `valida`; no `agregué` ni `agregando`.
3. Un commit de tipo `db` siempre incluye `schema.sql` **y** su migración. Nunca uno sin el otro.
4. Antes de hacer `git push`: `ruff check . && ruff format --check .` y `pytest` deben pasar.
5. Nunca se suben secretos, `.env`, datos de pacientes, Excel del hospital ni imágenes clínicas.
6. Si el CI queda en rojo en GitHub, se corrige en el siguiente commit antes de seguir con otro paso.

## Ejemplos
    feat(api): agrega filtros al listado de pacientes
    db: agrega tablas de tratamientos e importador
    fix(api): rechaza documentos duplicados con formato distinto
    test(api): cubre filtros del listado de pacientes
    ci: quita el job de migración hasta tener Supabase
    docs: agrega estándar de commits

## Activar la plantilla (una vez por persona, dentro del repo)
    git config commit.template .gitmessage