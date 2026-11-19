-- Arranque de una instalación: el PRIMER administrador (los demás se crean desde la pantalla "Gestión de profesionales").
-- Ejecutar una sola vez en Supabase > SQL Editor, DESPUÉS de crear el usuario en Authentication > Users > Add user
-- (correo + contraseña, con "Auto Confirm User"). Cambia el correo y el documento por los reales.

-- 1) Rol de administrador en el proveedor de identidad
update auth.users
set raw_app_meta_data = coalesce(raw_app_meta_data, '{}'::jsonb) || '{"roles":["administrador"]}'::jsonb
where email = 'CORREO_DEL_ADMIN';

-- 2) Su fila de profesional, enlazada a la cuenta (así "Perfil de usuario" muestra sus datos)
insert into public.profesional (nombre, identificacion, correo, especializacion, auth_id, activo)
select 'NOMBRE DEL ADMIN', 'DOCUMENTO', u.email, null, u.id::text, true
from auth.users u
where u.email = 'CORREO_DEL_ADMIN'
on conflict (auth_id) do nothing;

-- 3) Comprobación: debe mostrar 1 fila con roles ["administrador"] y tiene_profesional = true
select u.email, u.raw_app_meta_data->'roles' as roles,
       exists (select 1 from public.profesional p where p.auth_id = u.id::text) as tiene_profesional
from auth.users u where u.email = 'CORREO_DEL_ADMIN';
-- Después, la persona debe cerrar sesión y volver a entrar para que su token traiga el rol.
