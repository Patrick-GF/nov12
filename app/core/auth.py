"""Autenticación y gestión de sesión/perfiles (sin tablas nuevas).

- Guardia y Administrador: cuentas definidas en .streamlit/secrets.toml, sección [auth],
  guardadas solo como hash PBKDF2-HMAC-SHA256 con sal.
- Conductor: se identifica con su RUT (debe existir y estar 'Activo' en la tabla
  `conductores`) más la clave de conductores definida en [auth.conductores].
- Sesión: st.session_state guarda al usuario; main.py arma el menú (st.navigation)
  según su rol, de modo que cada perfil solo tiene registradas sus propias vistas.
"""
import base64
import hashlib
import hmac
import secrets

import streamlit as st

from core.db import tabla

ITERACIONES = 200_000
MAX_INTENTOS = 5
CUENTAS_FIJAS = {"guardia": "guardia", "admin": "admin"}  # usuario -> rol


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def hash_password(password: str) -> str:
    sal = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), sal, ITERACIONES)
    return f"pbkdf2_sha256${ITERACIONES}${_b64(sal)}${_b64(dk)}"


def verify_password(password: str, almacenado: str) -> bool:
    try:
        _, iters, sal, dk = almacenado.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(sal), int(iters))
        return hmac.compare_digest(calc, base64.b64decode(dk))
    except (ValueError, TypeError):
        return False


def normalizar_username(valor: str) -> str:
    """Minúsculas, sin puntos ni espacios (permite escribir el RUT de varias formas)."""
    return valor.strip().lower().replace(".", "").replace(" ", "")


def autenticar(username: str, password: str) -> dict | None:
    u = normalizar_username(username)
    cfg = st.secrets["auth"]

    if u in CUENTAS_FIJAS:
        cuenta = cfg[u]
        if verify_password(password, cuenta["password_hash"]):
            return {"username": u, "nombre": cuenta["nombre"], "rol": CUENTAS_FIJAS[u], "rut_conductor": None}
        return None

    # Conductor: RUT existente y activo + clave de conductores
    conductores = tabla("conductores").select("rut,nombre_completo,estado").execute().data
    for c in conductores:
        if normalizar_username(c["rut"]) == u and c["estado"] == "Activo":
            if verify_password(password, cfg["conductores"]["password_hash"]):
                return {"username": u, "nombre": c["nombre_completo"], "rol": "conductor", "rut_conductor": c["rut"]}
            return None
    return None


def intentos_agotados() -> bool:
    return st.session_state.get("intentos_fallidos", 0) >= MAX_INTENTOS


def registrar_intento_fallido() -> None:
    st.session_state["intentos_fallidos"] = st.session_state.get("intentos_fallidos", 0) + 1


def iniciar_sesion(usuario: dict) -> None:
    st.session_state["usuario"] = usuario
    st.session_state["intentos_fallidos"] = 0


def cerrar_sesion() -> None:
    for k in list(st.session_state.keys()):
        del st.session_state[k]


def usuario_actual() -> dict | None:
    return st.session_state.get("usuario")


def exigir_rol(*roles: str) -> dict:
    """Defensa en profundidad: aborta la vista si el rol de la sesión no corresponde."""
    u = usuario_actual()
    if not u or u["rol"] not in roles:
        st.error("No tienes permisos para ver esta sección.")
        st.stop()
    return u
