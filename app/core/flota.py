"""Reglas de negocio de la flota: reportes de estado, parámetros críticos y semáforo.

Sin triggers en la BD: al registrar un reporte crítico, la aplicación actualiza la tabla
maestra `vehiculos` a 'Requiere Mantención'. Los parámetros críticos se marcan en
`reportes_estado.observaciones` con etiquetas ([CRÍTICO:FRENOS], [CRÍTICO:NEUMATICOS]),
convención ya presente en los datos existentes.
"""
import pandas as pd

from core.db import ahora_iso, tabla

TAG_FRENOS = "[CRÍTICO:FRENOS]"
TAG_NEUMATICOS = "[CRÍTICO:NEUMATICOS]"
ETIQUETAS = {TAG_FRENOS: "Falla en sistema de frenos", TAG_NEUMATICOS: "Presión de neumáticos severamente baja"}
ESTADOS_VEHICULO = ["Operativo", "Requiere Mantención", "Crítico"]


def motivos_criticos(observaciones: str | None) -> list[str]:
    return [txt for tag, txt in ETIQUETAS.items() if tag in (observaciones or "")]


def registrar_reporte(*, patente: str, rut: str, km: int, combustible: int, neumaticos_ok: bool,
                      neumaticos_severo: bool, luces_ok: bool, frenos_falla: bool,
                      observaciones: str, foto_ruta: str | None) -> dict:
    """Inserta el reporte y aplica la regla: parámetro crítico => 'Requiere Mantención'."""
    tags = ([TAG_FRENOS] if frenos_falla else []) + ([TAG_NEUMATICOS] if neumaticos_severo else [])
    obs = " ".join(tags + ([observaciones.strip()] if observaciones.strip() else [])) or None
    reporte = tabla("reportes_estado").insert({
        "patente": patente, "rut_conductor": rut, "fecha_reporte": ahora_iso(),
        "kilometraje_salida": km, "nivel_combustible": combustible,
        "presion_neumaticos": neumaticos_ok, "luces_operativas": luces_ok,
        "observaciones": obs, "foto_evidencia_url": foto_ruta,
    }).execute().data[0]

    veh = tabla("vehiculos").select("kilometraje_actual,estado_operativo").eq("patente", patente).single().execute().data
    cambios = {"kilometraje_actual": max(int(veh["kilometraje_actual"]), km)}
    motivos = motivos_criticos(obs)
    if motivos and veh["estado_operativo"] == "Operativo":
        cambios["estado_operativo"] = "Requiere Mantención"
    tabla("vehiculos").update(cambios).eq("patente", patente).execute()
    return {"reporte": reporte, "motivos": motivos, "estado_cambiado": "estado_operativo" in cambios}


def semaforo(vehiculo: dict, ultimo: dict | None) -> str:
    if vehiculo["estado_operativo"] in ("Requiere Mantención", "Crítico"):
        return "Rojo"
    if ultimo and (ultimo["nivel_combustible"] < 25 or not ultimo["presion_neumaticos"]
                   or not ultimo["luces_operativas"] or motivos_criticos(ultimo["observaciones"])):
        return "Amarillo"
    return "Verde"


def estado_flota() -> pd.DataFrame:
    vehiculos = tabla("vehiculos").select("*").order("patente").execute().data
    ultimos: dict[str, dict] = {}
    for r in tabla("reportes_estado").select("*").order("fecha_reporte", desc=True).limit(1000).execute().data:
        ultimos.setdefault(r["patente"], r)  # el primero de cada patente es el más reciente
    df = pd.DataFrame(vehiculos)
    if df.empty:
        return df
    df["semaforo"] = [semaforo(v, ultimos.get(v["patente"])) for v in vehiculos]
    return df
