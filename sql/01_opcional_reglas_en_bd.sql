-- =====================================================================
-- OPCIONAL: reglas de negocio dentro de la base de datos
-- Ejecutar DESPUÉS de 00_esquema_base.sql, en un proyecto con acceso SQL.
--
-- La aplicación NO depende de este script: ya aplica estas mismas reglas desde
-- Python (app/core). Sirve para que la BD las garantice también ante inserciones
-- hechas por otras vías. Es idempotente y no agrega tablas ni columnas.
-- =====================================================================

-- 1. Restricciones que el esquema base no declara
do $$ begin
  alter table public.vehiculos add constraint vehiculos_estado_chk
    check (estado_operativo in ('Operativo', 'Requiere Mantención', 'Crítico'));
exception when others then raise notice 'vehiculos_estado_chk: %', sqlerrm; end $$;

do $$ begin
  alter table public.conductores add constraint conductores_estado_chk
    check (estado in ('Activo', 'Suspendido', 'En Comisión'));
exception when others then raise notice 'conductores_estado_chk: %', sqlerrm; end $$;

-- Un conductor no puede tener dos autorizaciones vigentes para la misma patente
do $$ begin
  create unique index if not exists autorizaciones_vigente_uidx
    on public.autorizaciones (patente, rut_conductor) where vigente;
exception when others then raise notice 'autorizaciones_vigente_uidx: %', sqlerrm; end $$;

create index if not exists reportes_patente_fecha_idx on public.reportes_estado (patente, fecha_reporte desc);

-- 2. Automatización: parámetro crítico => vehículo "Requiere Mantención"
--    Los parámetros críticos se marcan en observaciones con las etiquetas
--    [CRÍTICO:FRENOS] y [CRÍTICO:NEUMATICOS] (misma convención que usa la app).
create or replace function public.fn_actualizar_vehiculo()
returns trigger language plpgsql as $$
begin
  update public.vehiculos v
     set kilometraje_actual = greatest(v.kilometraje_actual, new.kilometraje_salida),
         estado_operativo   = case
                                when position('[CRÍTICO:' in coalesce(new.observaciones, '')) > 0
                                     and v.estado_operativo = 'Operativo'
                                  then 'Requiere Mantención'
                                else v.estado_operativo
                              end
   where v.patente = new.patente;
  return new;
end $$;

drop trigger if exists trg_actualizar_vehiculo on public.reportes_estado;
create trigger trg_actualizar_vehiculo
  after insert on public.reportes_estado
  for each row execute function public.fn_actualizar_vehiculo();

-- 3. Consulta cruzada del guardia en una sola consulta (equivale a core/acceso.py)
create or replace function public.validar_acceso(p_patente text)
returns table (
  resultado text, motivo text, patente text, tipo_vehiculo text, marca_modelo text,
  estado_operativo text, kilometraje_actual integer, rut_conductor text,
  nombre_conductor text, grado_o_cargo text, unidad_destino text
)
language sql stable as $$
  select
    case
      when v.id is null                          then 'Denegado'
      when a.id is null                          then 'Denegado'
      when c.id is null or c.estado <> 'Activo'  then 'Denegado'
      when v.estado_operativo <> 'Operativo'     then 'Alerta de Estado'
      else 'Autorizado'
    end,
    case
      when v.id is null                          then 'Patente no registrada en el catálogo'
      when a.id is null                          then 'Sin autorización vigente para esta patente'
      when c.id is null or c.estado <> 'Activo'  then 'Conductor no habilitado (' || coalesce(c.estado, 'sin registro') || ')'
      when v.estado_operativo <> 'Operativo'     then 'Vehículo en estado: ' || v.estado_operativo
      else 'Conductor habilitado y vehículo operativo'
    end,
    v.patente, v.tipo_vehiculo, v.marca_modelo, v.estado_operativo, v.kilometraje_actual::integer,
    c.rut, c.nombre_completo, c.grado_o_cargo, c.unidad_destino
  from (select upper(regexp_replace(coalesce(p_patente, ''), '[^A-Za-z0-9]', '', 'g')) as p) q
  left join public.vehiculos v on upper(regexp_replace(v.patente, '[^A-Za-z0-9]', '', 'g')) = q.p
  left join public.autorizaciones a on a.patente = v.patente and a.vigente
  left join public.conductores c on c.rut = a.rut_conductor;
$$;

-- 4. Semáforo por vehículo (Verde / Amarillo / Rojo), igual que core/flota.py
create or replace view public.v_estado_flota with (security_invoker = true) as
select
  v.patente, v.tipo_vehiculo, v.marca_modelo, v.anio, v.kilometraje_actual, v.estado_operativo,
  r.fecha_reporte as ultimo_reporte,
  case
    when v.estado_operativo in ('Requiere Mantención', 'Crítico') then 'Rojo'
    when r.id is not null and (r.nivel_combustible < 25
                               or not r.presion_neumaticos
                               or not r.luces_operativas
                               or position('[CRÍTICO:' in coalesce(r.observaciones, '')) > 0) then 'Amarillo'
    else 'Verde'
  end as semaforo
from public.vehiculos v
left join lateral (
  select x.* from public.reportes_estado x
   where x.patente = v.patente
   order by x.fecha_reporte desc, x.id desc limit 1
) r on true;

-- 5. Storage: bucket de evidencias (800 KB por imagen). Permite JSON porque la bitácora de accesos se guarda ahí.
--    No modifica uno ya existente (si ya existe, ver update de allowed_mime_types en el README).
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('evidencias-vehiculares', 'evidencias-vehiculares', false, 819200,
        array['image/jpeg', 'image/png', 'image/webp', 'application/json'])
on conflict (id) do nothing;
