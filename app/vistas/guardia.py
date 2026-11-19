"""Perfil Guardia de Garita: consulta cruzada de patente y registro del acceso."""
import hashlib
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from core.acceso import cargar_eventos, registrar_evento, validar_acceso
from core.auth import exigir_rol
from core.placas import leer_patente_ocr, normalizar_patente, patente_valida

ESTILOS = {
    "Autorizado": ("#1b8a3a", "✅ AUTORIZADO"),
    "Denegado": ("#c62828", "⛔ DENEGADO"),
    "Alerta de Estado": ("#e08e00", "⚠️ ALERTA DE ESTADO"),
}


@st.cache_data(show_spinner="Leyendo patente…")
def _ocr(huella: str, datos: bytes) -> str | None:
    return leer_patente_ocr(datos)


def _banner(resultado: str, motivo: str) -> None:
    color, titulo = ESTILOS[resultado]
    st.markdown(
        f"<div style='background:{color};color:#fff;padding:1.2rem;border-radius:12px;text-align:center'>"
        f"<div style='font-size:2rem;font-weight:700'>{titulo}</div>"
        f"<div style='font-size:1.05rem'>{motivo}</div></div>",
        unsafe_allow_html=True,
    )


def control_acceso() -> None:
    usuario = exigir_rol("guardia")
    st.title("🛂 Control de acceso vehicular")

    modo = st.radio("Ingreso de patente", ["Escribir", "Escanear con cámara"], horizontal=True)
    foto_bytes: bytes | None = None
    sugerida = ""
    if modo == "Escanear con cámara":
        foto = st.camera_input("Fotografía de la patente")
        if foto:
            foto_bytes = foto.getvalue()
            sugerida = _ocr(hashlib.md5(foto_bytes).hexdigest(), foto_bytes) or ""
            if not sugerida:
                st.info("No se pudo leer la patente automáticamente; escríbela abajo.")
    patente_txt = st.text_input("Patente", value=sugerida, max_chars=10, placeholder="ABCD-12")

    if st.button("Verificar autorización", type="primary", width="stretch"):
        patente = normalizar_patente(patente_txt)
        if not patente_valida(patente):
            st.warning("Formato de patente no válido (ej.: ABCD-12).")
        else:
            try:
                filas = validar_acceso(patente)
            except Exception as e:
                st.error(f"Error al consultar la base de datos: {e}")
                return
            st.session_state["guardia_consulta"] = {"patente": patente, "filas": filas, "foto": foto_bytes}

    consulta = st.session_state.get("guardia_consulta")
    if consulta:
        _mostrar_resolucion(consulta, usuario)

    st.divider()
    st.subheader("Últimos registros")
    try:
        eventos = cargar_eventos(date.today() - timedelta(days=2))
    except Exception as e:
        st.error(f"No se pudo leer la bitácora: {e}")
        eventos = []
    recientes = [
        {k: e[k] for k in ("fecha_hora", "patente_consultada", "resultado", "motivo", "rut_conductor")}
        for e in eventos if e["guardia"] == usuario["username"]
    ][:10]
    if recientes:
        st.dataframe(pd.DataFrame(recientes), width="stretch", hide_index=True)
    else:
        st.caption("Aún no has registrado accesos.")


def _mostrar_resolucion(consulta: dict, usuario: dict) -> None:
    filas = consulta["filas"]
    # Orden de preferencia: si algún conductor está Autorizado, ese es el resultado a destacar.
    prioridad = {"Autorizado": 0, "Alerta de Estado": 1, "Denegado": 2}
    filas = sorted(filas, key=lambda f: prioridad[f["resultado"]])
    admitidas = [f for f in filas if f["resultado"] != "Denegado"]

    elegida = filas[0]
    if len(admitidas) > 1:
        etiquetas = [f"{f['nombre_conductor']} · {f['grado_o_cargo']}" for f in admitidas]
        idx = st.selectbox("Conductores autorizados para esta patente: ¿quién ingresa?", range(len(admitidas)),
                           format_func=lambda i: etiquetas[i])
        elegida = admitidas[idx]

    _banner(elegida["resultado"], elegida["motivo"])
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Vehículo**")
        if elegida["patente"]:
            st.write(f"{elegida['patente']} — {elegida['marca_modelo']} ({elegida['tipo_vehiculo']})")
            st.write(f"Estado: **{elegida['estado_operativo']}** · {elegida['kilometraje_actual']:,} km")
        else:
            st.write(f"{consulta['patente']} — no registrada")
    with c2:
        st.markdown("**Conductor**")
        if elegida["rut_conductor"]:
            st.write(f"{elegida['nombre_conductor']} ({elegida['grado_o_cargo']})")
            st.write(f"{elegida['unidad_destino']} · RUT {elegida['rut_conductor']}")
        else:
            st.write("Sin conductor autorizado")

    if st.button("Registrar evento en bitácora", width="stretch"):
        try:
            registrar_evento(consulta["patente"], elegida, usuario["username"], consulta["foto"])
            st.success("Evento registrado.")
            del st.session_state["guardia_consulta"]
            st.rerun()
        except Exception as e:
            st.error(f"No se pudo registrar el evento: {e}")
