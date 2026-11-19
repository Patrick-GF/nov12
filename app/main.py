"""Punto de entrada: streamlit run app/main.py  (desde la raíz del repositorio)."""
import streamlit as st

st.set_page_config(page_title="Control de Flota", page_icon="🚙", layout="wide")

from core.auth import (  # noqa: E402
    autenticar,
    cerrar_sesion,
    intentos_agotados,
    iniciar_sesion,
    registrar_intento_fallido,
    usuario_actual,
)
from vistas import admin, conductor, guardia  # noqa: E402

ROLES_ETIQUETA = {"guardia": "Guardia de Garita", "conductor": "Conductor Operativo", "admin": "Puesto de Mando"}


def pagina_login() -> None:
    _, centro, _ = st.columns([1, 2, 1])
    with centro:
        st.title("🚙 Control de Flota")
        st.caption("Ingresa con tu usuario (guardia/administrador) o con tu RUT (conductor).")
        with st.form("login"):
            usuario = st.text_input("Usuario o RUT")
            clave = st.text_input("Contraseña", type="password")
            enviar = st.form_submit_button("Ingresar", type="primary", width="stretch")
        if enviar:
            if intentos_agotados():
                st.error("Demasiados intentos fallidos. Recarga la página para reintentar.")
                return
            try:
                u = autenticar(usuario, clave)
            except Exception as e:  # tabla 'usuarios' inexistente, red caída, etc.
                st.error(
                    "No se pudo consultar la base de datos o falta la sección [auth] en secrets.toml. "
                    f"¿Ejecutaste scripts/generar_credenciales.py?\n\nDetalle: {e}"
                )
                return
            if u:
                iniciar_sesion(u)
                st.rerun()
            registrar_intento_fallido()
            st.error("Credenciales inválidas.")


def menu_por_rol(rol: str) -> list:
    if rol == "guardia":
        return [st.Page(guardia.control_acceso, title="Control de acceso", icon="🛂", url_path="acceso")]
    if rol == "conductor":
        return [st.Page(conductor.checkin, title="Check-in operativo", icon="📝", url_path="checkin")]
    return [
        st.Page(admin.monitoreo, title="Monitoreo operativo", icon="📊", url_path="monitoreo"),
        st.Page(admin.analitica, title="Analítica de uso", icon="📈", url_path="analitica"),
        st.Page(admin.auditoria, title="Auditoría de incidencias", icon="🔎", url_path="auditoria"),
        st.Page(admin.gestion, title="Gestión", icon="⚙️", url_path="gestion"),
    ]


usuario = usuario_actual()
if not usuario:
    pg = st.navigation([st.Page(pagina_login, title="Ingreso", url_path="ingreso")], position="hidden")
else:
    pg = st.navigation(menu_por_rol(usuario["rol"]))
    with st.sidebar:
        st.markdown(f"**{usuario['nombre']}**  \n{ROLES_ETIQUETA[usuario['rol']]}")
        st.button("Cerrar sesión", on_click=cerrar_sesion, width="stretch")
pg.run()
