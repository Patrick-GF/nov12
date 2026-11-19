"""Exporta las tablas de Supabase a CSV y Excel.

Las credenciales se leen de .streamlit/secrets.toml (ignorado por git),
nunca se escriben en el código.
"""
import tomllib
from pathlib import Path

import pandas as pd
from supabase import create_client

secretos = tomllib.loads(Path(".streamlit/secrets.toml").read_text(encoding="utf-8"))
supabase = create_client(secretos["supabase"]["url"], secretos["supabase"]["key"])

tablas = ["conductores", "vehiculos", "autorizaciones", "reportes_estado"]

for tabla in tablas:
    respuesta = supabase.table(tabla).select("*").execute()
    datos = respuesta.data

    if datos:
        df = pd.DataFrame(datos)
        df.to_csv(f"{tabla}.csv", index=False, encoding="utf-8-sig")
        df.to_excel(f"{tabla}.xlsx", index=False)
        print(f"Tabla {tabla} descargada correctamente.")
    else:
        print(f"La tabla {tabla} está vacía.")
