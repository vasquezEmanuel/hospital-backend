-- ============================================================================
-- Seguridad de la base de datos (Sprint 5) — permisos mínimos para la API.
-- Ejecutar en Supabase (SQL Editor) con el usuario postgres, DESPUÉS de las migraciones.
-- Es idempotente: se puede repetir (hay que repetirlo cuando una migración cree tablas nuevas o cuando un sprint
-- agregue escrituras nuevas a la API; ver "ESCRITURAS DE LA API" más abajo).
--
-- ANTES de ejecutarlo: cambie CAMBIAR_ESTA_CONTRASENA por una contraseña larga de solo letras y números.
-- Si el rol ya existe, la contraseña NO se toca (cámbiela con ALTER ROLE hospital_api PASSWORD '...').
--
-- Qué consigue: la API se conecta como `hospital_api`, que NO puede borrar filas, vaciar tablas, modificar el
-- esquema, ni tocar la auditoría más que insertando. Si alguien robara las credenciales de la API, el daño posible
-- sería mucho menor que con `postgres`. Las migraciones y el ETL siguen corriendo con el usuario propietario.
-- ============================================================================

-- 1) Rol de la API (sin privilegios especiales; sujeto a RLS).
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'hospital_api') THEN
    CREATE ROLE hospital_api LOGIN PASSWORD 'CAMBIAR_ESTA_CONTRASENA'
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  END IF;
END $$;

GRANT USAGE ON SCHEMA public TO hospital_api;

-- 2) Privilegios por tabla. Se parte de cero y se concede lo mínimo.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM hospital_api;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM hospital_api;

-- Lectura de todo lo de negocio (menos alembic_version, que solo usan las migraciones).
DO $$ DECLARE t text; BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'alembic_version' LOOP
    EXECUTE format('GRANT SELECT ON public.%I TO hospital_api', t);
  END LOOP;
END $$;

-- ESCRITURAS DE LA API: pacientes e imágenes se crean y modifican; la auditoría solo se inserta; (Sprint 7) las
-- atenciones se crean con sus diagnósticos y tratamientos (solo INSERT: una atención registrada no se reescribe), y los
-- catálogos aseguradora / tratamiento / profesional se crean y editan (inactivar = UPDATE de `activo`).
-- Cuando un sprint agregue escrituras, se añaden aquí y en la sección 4.
GRANT INSERT, UPDATE ON public.paciente, public.imagen_clinica TO hospital_api;
GRANT INSERT ON public.auditoria TO hospital_api;
GRANT INSERT ON public.atencion, public.diagnostico_hospitalario, public.diagnostico_bucal,
                public.cie10_x_diagnostico_bucal, public.atencion_x_tratamiento TO hospital_api;
GRANT INSERT, UPDATE ON public.aseguradora, public.tratamiento, public.profesional TO hospital_api;
-- Sprint 8: importaciones. cie10 solo INSERT (el catálogo se carga una vez por el endpoint; editarlo cambia qué códigos
-- acepta la regla 2, así que UPDATE/DELETE siguen siendo solo del propietario, por consola).
GRANT INSERT ON public.cie10 TO hospital_api;
GRANT INSERT, UPDATE ON public.importacion, public.importacion_fila TO hospital_api;
-- Secuencias (llaves autonumeradas) de las tablas donde la API inserta; se buscan por tabla, no por nombre.
DO $$ DECLARE t text; s text; BEGIN
  FOREACH t IN ARRAY ARRAY['paciente','imagen_clinica','auditoria','atencion','diagnostico_hospitalario',
                           'diagnostico_bucal','aseguradora','tratamiento','profesional',
                           'importacion','importacion_fila'] LOOP
    FOR s IN SELECT pg_get_serial_sequence('public.' || t, a.attname)
             FROM pg_attribute a
             WHERE a.attrelid = ('public.' || t)::regclass AND a.attnum > 0 AND NOT a.attisdropped
               AND pg_get_serial_sequence('public.' || t, a.attname) IS NOT NULL LOOP
      EXECUTE format('GRANT USAGE ON SEQUENCE %s TO hospital_api', s);
    END LOOP;
  END LOOP;
END $$;
-- Nunca se concede DELETE ni TRUNCATE: el borrado es lógico (regla 5) y la auditoría es inmutable (regla 6).

-- 3) Row Level Security: activada en TODAS las tablas. Sin políticas, nadie la atraviesa (ni la API pública de
--    Supabase); el usuario postgres la ignora, y hospital_api solo pasa por las políticas de la sección 4.
DO $$ DECLARE t text; BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
  END LOOP;
END $$;

-- 4) Políticas de hospital_api (solo lo que sus privilegios ya permiten).
DO $$ DECLARE t text; BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'alembic_version' LOOP
    EXECUTE format('DROP POLICY IF EXISTS api_leer ON public.%I', t);
    EXECUTE format('CREATE POLICY api_leer ON public.%I FOR SELECT TO hospital_api USING (true)', t);
  END LOOP;
END $$;

DROP POLICY IF EXISTS api_insertar ON public.paciente;
CREATE POLICY api_insertar ON public.paciente FOR INSERT TO hospital_api WITH CHECK (true);
DROP POLICY IF EXISTS api_actualizar ON public.paciente;
CREATE POLICY api_actualizar ON public.paciente FOR UPDATE TO hospital_api USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS api_insertar ON public.imagen_clinica;
CREATE POLICY api_insertar ON public.imagen_clinica FOR INSERT TO hospital_api WITH CHECK (true);
DROP POLICY IF EXISTS api_actualizar ON public.imagen_clinica;
CREATE POLICY api_actualizar ON public.imagen_clinica FOR UPDATE TO hospital_api USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS api_insertar ON public.auditoria;
CREATE POLICY api_insertar ON public.auditoria FOR INSERT TO hospital_api WITH CHECK (true);

-- Sprint 7: atenciones, sus diagnósticos y tratamientos (solo INSERT) y catálogos (INSERT/UPDATE).
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['atencion','diagnostico_hospitalario','diagnostico_bucal','cie10_x_diagnostico_bucal',
                           'atencion_x_tratamiento','aseguradora','tratamiento','profesional'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS api_insertar ON public.%I', t);
    EXECUTE format('CREATE POLICY api_insertar ON public.%I FOR INSERT TO hospital_api WITH CHECK (true)', t);
  END LOOP;
  FOREACH t IN ARRAY ARRAY['aseguradora','tratamiento','profesional'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS api_actualizar ON public.%I', t);
    EXECUTE format('CREATE POLICY api_actualizar ON public.%I FOR UPDATE TO hospital_api USING (true) WITH CHECK (true)', t);
  END LOOP;
END $$;

-- Sprint 8: importaciones (cie10 solo INSERT; importacion e importacion_fila INSERT/UPDATE).
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['cie10','importacion','importacion_fila'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS api_insertar ON public.%I', t);
    EXECUTE format('CREATE POLICY api_insertar ON public.%I FOR INSERT TO hospital_api WITH CHECK (true)', t);
  END LOOP;
  FOREACH t IN ARRAY ARRAY['importacion','importacion_fila'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS api_actualizar ON public.%I', t);
    EXECUTE format('CREATE POLICY api_actualizar ON public.%I FOR UPDATE TO hospital_api USING (true) WITH CHECK (true)', t);
  END LOOP;
END $$;
