"""Verifica que schema.sql (fuente de verdad) y `alembic upgrade head` producen el MISMO esquema.

Uso: python scripts/check_schema_drift.py <url_bd_con_schema.sql> <url_bd_con_alembic>
Compara columnas, restricciones, índices, triggers y cuerpos de funciones. Falla (exit 1) si difieren.
"""

import sys

import psycopg

CONSULTAS = {
    "columnas": """SELECT table_name, column_name, data_type, character_maximum_length, is_nullable,
                          regexp_replace(coalesce(column_default,''), 'nextval\\(.*', 'serial')
                   FROM information_schema.columns WHERE table_schema='public'""",
    "restricciones": """SELECT conrelid::regclass::text, contype::text, pg_get_constraintdef(oid)
                        FROM pg_constraint WHERE connamespace='public'::regnamespace""",
    "indices": """SELECT tablename, regexp_replace(indexdef, 'INDEX \\S+ ON', 'INDEX ON')
                  FROM pg_indexes WHERE schemaname='public'""",
    "triggers": """SELECT event_object_table, trigger_name, action_timing, event_manipulation, action_statement
                   FROM information_schema.triggers WHERE trigger_schema='public'""",
    "funciones": """SELECT proname, regexp_replace(prosrc, '\\s+', ' ', 'g')
                    FROM pg_proc WHERE pronamespace='public'::regnamespace""",
}


def esquema(url: str) -> dict[str, set]:
    with psycopg.connect(url) as conn:
        resultado = {k: {tuple(map(str, r)) for r in conn.execute(q).fetchall()} for k, q in CONSULTAS.items()}
    # alembic_version es tabla interna de Alembic: no forma parte del esquema de negocio.
    return {k: {r for r in v if "alembic_version" not in r[0]} for k, v in resultado.items()}


def main(url_a: str, url_b: str) -> int:
    a, b = esquema(url_a), esquema(url_b)
    hay_drift = False
    for clave in CONSULTAS:
        solo_a, solo_b = a[clave] - b[clave], b[clave] - a[clave]
        if solo_a or solo_b:
            hay_drift = True
            print(f"\n[DRIFT] {clave}")
            for r in sorted(solo_a):
                print("  solo en schema.sql :", r)
            for r in sorted(solo_b):
                print("  solo en migraciones:", r)
    print(
        "Esquema consistente: schema.sql == alembic upgrade head"
        if not hay_drift
        else "\nschema.sql y las migraciones divergen"
    )
    return 1 if hay_drift else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
