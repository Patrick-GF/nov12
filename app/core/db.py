"""Conexión a Supabase. Las credenciales viven solo en .streamlit/secrets.toml."""
import streamlit as st
from supabase import Client, create_client


@st.cache_resource(show_spinner=False)
def get_client() -> Client:
    cfg = st.secrets["supabase"]
    return create_client(cfg["url"], cfg["key"])


def tabla(nombre: str):
    return get_client().table(nombre)


def ahora_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
