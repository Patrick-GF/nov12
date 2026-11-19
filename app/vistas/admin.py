"""Perfil Administrador de Puesto de Mando: monitoreo, analítica, auditoría y gestión."""
from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from core.acceso import cargar_eventos
from core.auth import exigir_rol
from core.db import ahora_iso, tabla
from core.flota import ESTADOS_VEHICULO, estado_flota, motivos_criticos
from core.storage import url_firmada

COLORES = {"Verde": "#1b8a3a", "Amarillo": "#f2b705", "Rojo": "#c62828"}
TEXTO = {"Verde": "#ffffff", "Amarillo": "#1a1a1a", "Rojo": "#ffffff"}


def _df(datos: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(datos)


@st.cache_data(ttl=30, show_spinner=False)
def _vehiculos() -> pd.DataFrame:
    return _df(tabla("vehiculos").select("*").order("patente").execute().data)


@st.cache_data(ttl=30, show_spinner=False)
def _conductores() -> pd.DataFrame:
    return _df(tabla("conductores").select("*").order("nombre_completo").execute().data)


@st.cache_data(ttl=60, show_spinner="Leyendo bitácora de accesos…")
def _eventos(desde: date, patente: str | None = None) -> list[dict]:
    return cargar_eventos(desde, patente)


# ---------------------------------------------------------------- Monitoreo
@st.fragment(run_every=15)
def _panel_monitoreo() -> None:
    flota = estado_flota()
    if flota.empty:
        st.info("No hay vehículos registrados.")
        return
    total = len(flota)
    operativos = int((flota["estado_operativo"] == "Operativo").sum())
    inmovilizados = int(flota["estado_operativo"].isin(["Requiere Mantención", "Crítico"]).sum())
    amarillos = int((flota["semaforo"] == "Amarillo").sum())

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Disponibilidad de la flota", f"{operativos / total:.0%}", f"{operativos} de {total} operativos", delta_color="off")
    m2.metric("Inmovilizadas / mantención urgente", inmovilizados)
    m3.metric("Con alerta leve (amarillo)", amarillos)
    m4.metric("Total de unidades", total)

    st.subheader("Matriz de estado por vehículo")
    columnas = st.columns(5)
    for i, v in flota.iterrows():
        s = v["semaforo"]
        columnas[i % 5].markdown(
            f"<div style='background:{COLORES[s]};color:{TEXTO[s]};padding:.7rem;border-radius:10px;margin-bottom:.6rem'>"
            f"<b>{v['patente']}</b><br><small>{v['marca_modelo']}</small><br>"
            f"<b>{s.upper()}</b> · {v['estado_operativo']}</div>",
            unsafe_allow_html=True,
        )

    st.subheader("Alertas por fallas mecánicas")
    alertas = _df(
        tabla("reportes_estado")
        .select("fecha_reporte,patente,rut_conductor,observaciones")
        .ilike("observaciones", "%CRÍTICO:%")
        .order("fecha_reporte", desc=True)
        .limit(10)
        .execute()
        .data
    )
    if alertas.empty:
        st.success("Sin alertas críticas registradas.")
    else:
        alertas["falla"] = alertas["observaciones"].map(lambda o: "; ".join(motivos_criticos(o)))
        st.dataframe(alertas, width="stretch", hide_index=True)
    st.caption("Actualización automática cada 15 s.")


ICONO = {"Autorizado": "🟢", "Alerta de Estado": "🟡", "Denegado": "🔴"}


@st.fragment(run_every=30)
def _feed_accesos() -> None:
    """Feed cronológico global de accesos (más recientes primero) con evidencia fotográfica."""
    st.subheader("Feed de accesos en garita")
    c1, c2 = st.columns([1, 2])
    cantidad = c1.slider("Eventos a mostrar", 5, 30, 10, step=5)
    resultados = c2.multiselect(
        "Resultado", list(ICONO), default=list(ICONO), key="feed_resultado",
    )
    eventos = [e for e in _eventos(date.today() - timedelta(days=7)) if e["resultado"] in resultados]
    if not eventos:
        st.info("No hay accesos registrados en los últimos 7 días.")
        return
    nombres = dict(zip(_conductores()["rut"], _conductores()["nombre_completo"]))
    for e in eventos[:cantidad]:
        col_foto, col_txt = st.columns([1, 4])
        url = url_firmada(e.get("foto"))
        if url:
            col_foto.image(url, width=110)
        else:
            col_foto.caption("Sin foto")
        patente = e.get("patente") or e.get("patente_consultada") or "—"
        col_txt.markdown(
            f"{ICONO.get(e['resultado'], '⚪')} **{e['resultado']}** · `{patente}` · "
            f"{e['fecha_hora'][:19].replace('T', ' ')} UTC  \n"
            f"{e['motivo']}  \n"
            f"<small>Conductor: {nombres.get(e.get('rut_conductor'), '—')} · "
            f"Unidad: {e.get('unidad_destino') or '—'} · Guardia: {e.get('guardia', '—')}</small>",
            unsafe_allow_html=True,
        )
    st.caption(f"Mostrando {min(cantidad, len(eventos))} de {len(eventos)} eventos · actualización cada 30 s.")


def monitoreo() -> None:
    exigir_rol("admin")
    st.title("📊 Monitoreo operativo")
    _panel_monitoreo()
    st.divider()
    _feed_accesos()


# ---------------------------------------------------------------- Analítica
def analitica() -> None:
    exigir_rol("admin")
    st.title("📈 Analítica de uso y consumo")

    st.subheader("Kilometraje acumulado")
    veh = _vehiculos()
    if veh.empty:
        st.info("Sin datos de vehículos.")
    else:
        agrupar = st.radio("Agrupar por", ["Vehículo", "Tipo de vehículo"], horizontal=True)
        tipos = st.multiselect("Filtrar por tipo", sorted(veh["tipo_vehiculo"].unique()))
        datos = veh[veh["tipo_vehiculo"].isin(tipos)] if tipos else veh
        if agrupar == "Vehículo":
            graf = alt.Chart(datos).mark_bar().encode(
                x=alt.X("patente:N", sort="-y", title="Patente"),
                y=alt.Y("kilometraje_actual:Q", title="Km acumulado"),
                color=alt.Color("tipo_vehiculo:N", title="Tipo"),
                tooltip=["patente", "marca_modelo", "tipo_vehiculo", "kilometraje_actual"],
            )
        else:
            graf = alt.Chart(datos).mark_bar().encode(
                x=alt.X("tipo_vehiculo:N", sort="-y", title="Tipo"),
                y=alt.Y("sum(kilometraje_actual):Q", title="Km acumulado"),
                color=alt.Color("tipo_vehiculo:N", legend=None),
                tooltip=["tipo_vehiculo", alt.Tooltip("sum(kilometraje_actual):Q", title="Km"), "count()"],
            )
        st.altair_chart(graf.interactive(), width="stretch")

    st.subheader("Frecuencia de accesos por unidad / sector")
    c1, c2 = st.columns(2)
    desde = c1.date_input("Desde", date.today() - timedelta(days=30))
    resultados = c2.multiselect("Resultado", ["Autorizado", "Denegado", "Alerta de Estado"],
                                default=["Autorizado", "Denegado", "Alerta de Estado"])
    accesos = _df(_eventos(desde))
    if accesos.empty:
        st.info("No hay accesos registrados en el período.")
        return
    accesos = accesos[accesos["resultado"].isin(resultados)].copy()
    accesos["unidad_destino"] = accesos["unidad_destino"].fillna("Sin identificar")
    conteo = accesos.groupby(["unidad_destino", "resultado"]).size().reset_index(name="accesos")
    graf = alt.Chart(conteo).mark_bar().encode(
        y=alt.Y("unidad_destino:N", sort="-x", title="Unidad / sector"),
        x=alt.X("accesos:Q", title="Accesos", axis=alt.Axis(tickMinStep=1, format="d")),
        color=alt.Color("resultado:N", title="Resultado"),
        tooltip=["unidad_destino", "resultado", "accesos"],
    )
    st.altair_chart(graf, width="stretch")


# ---------------------------------------------------------------- Auditoría
def auditoria() -> None:
    exigir_rol("admin")
    st.title("🔎 Auditoría de incidencias")
    veh = _vehiculos()
    if veh.empty:
        st.info("Sin vehículos registrados.")
        return
    patente = st.selectbox("Patente", veh["patente"].tolist())
    nombres = dict(zip(_conductores()["rut"], _conductores()["nombre_completo"]))

    st.subheader("Informes de estado de los conductores")
    reportes = tabla("reportes_estado").select("*").eq("patente", patente).order("fecha_reporte", desc=True).execute().data
    if not reportes:
        st.caption("Sin reportes para esta patente.")
    for r in reportes:
        motivos = motivos_criticos(r["observaciones"])
        marca = "🔴" if motivos else "🟢"
        with st.expander(f"{marca} {r['fecha_reporte'][:16].replace('T', ' ')} · {nombres.get(r['rut_conductor'], r['rut_conductor'])}"):
            a, b = st.columns([2, 1])
            a.write(
                f"**Km:** {r['kilometraje_salida']:,} · **Combustible:** {r['nivel_combustible']}%  \n"
                f"**Neumáticos:** {'OK' if r['presion_neumaticos'] else 'Presión baja'} · "
                f"**Luces:** {'OK' if r['luces_operativas'] else 'Falla'}  \n"
                f"**Observaciones:** {r['observaciones'] or '—'}"
            )
            if motivos:
                a.error("; ".join(motivos))
            url = url_firmada(r.get("foto_evidencia_url"))
            if url:
                b.image(url, caption="Odómetro", width="stretch")
            else:
                b.caption("Sin fotografía")

    st.subheader("Historial de accesos (últimos 30 días)")
    accesos = _eventos(date.today() - timedelta(days=30), patente)
    if not accesos:
        st.caption("Sin accesos registrados para esta patente.")
    for a in accesos[:50]:
        with st.expander(f"{a['fecha_hora'][:16].replace('T', ' ')} · {a['resultado']}"):
            st.write(f"{a['motivo']} · Conductor: {nombres.get(a['rut_conductor'], '—')} · Guardia: {a['guardia']}")
            url = url_firmada(a.get("foto"))
            if url:
                st.image(url, caption="Patente", width=320)


# ---------------------------------------------------------------- Gestión
def gestion() -> None:
    exigir_rol("admin")
    st.title("⚙️ Gestión")
    tab_aut, tab_est = st.tabs(["Autorizaciones", "Estado de vehículos"])

    with tab_aut:
        veh, cond = _vehiculos(), _conductores()
        vigentes = _df(tabla("autorizaciones").select("*").eq("vigente", True).order("patente").execute().data)
        with st.form("nueva_aut", clear_on_submit=True):
            st.markdown("**Nueva autorización**")
            patente = st.selectbox("Vehículo", veh["patente"].tolist())
            activos = cond[cond["estado"] == "Activo"].set_index("rut")
            rut = st.selectbox("Conductor", activos.index.tolist(),
                               format_func=lambda r: f"{activos.loc[r, 'nombre_completo']} ({r})")
            if st.form_submit_button("Autorizar", type="primary"):
                ya = not vigentes.empty and ((vigentes["patente"] == patente) & (vigentes["rut_conductor"] == rut)).any()
                if ya:
                    st.warning("Ese conductor ya tiene una autorización vigente para esa patente.")
                else:
                    tabla("autorizaciones").insert(
                        {"patente": patente, "rut_conductor": rut, "vigente": True, "fecha_asignacion": ahora_iso()}
                    ).execute()
                    st.success("Autorización creada.")
                    st.rerun()

        st.markdown("**Autorizaciones vigentes**")
        if vigentes.empty:
            st.caption("No hay autorizaciones vigentes.")
        else:
            st.dataframe(vigentes, width="stretch", hide_index=True)
            indexado = vigentes.set_index("id")
            with st.form("revocar"):
                aid = st.selectbox("Revocar autorización", indexado.index.tolist(),
                                   format_func=lambda i: f"#{i} · {indexado.loc[i, 'patente']} → {indexado.loc[i, 'rut_conductor']}")
                if st.form_submit_button("Revocar"):
                    tabla("autorizaciones").update({"vigente": False}).eq("id", int(aid)).execute()
                    st.rerun()

    with tab_est:
        veh = _vehiculos().set_index("patente")
        with st.form("estado_veh"):
            patente = st.selectbox("Vehículo", veh.index.tolist(),
                                   format_func=lambda p: f"{p} · {veh.loc[p, 'estado_operativo']}")
            nuevo = st.selectbox("Nuevo estado", ESTADOS_VEHICULO)
            if st.form_submit_button("Actualizar estado", type="primary"):
                tabla("vehiculos").update({"estado_operativo": nuevo}).eq("patente", patente).execute()
                _vehiculos.clear()
                st.rerun()
