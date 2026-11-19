"""Control de acceso vehicular: consulta cruzada y bitácora de accesos.

Validación (3 consultas PostgREST sobre las tablas existentes):
  1. vehiculos        -> existe la patente y en qué estado está
  2. autorizaciones   -> conductores con autorización vigente para esa patente
  3. conductores      -> datos y estado (Activo) de esos conductores
Bitácora: cada evento es un objeto JSON en el bucket (accesos/AAAA-MM-DD/...json),
con su fotografía opcional junto a él.
"""
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone

from core.db import tabla
from core.storage import comprimir_imagen, descargar_json, listar, subir_bytes, subir_json


def _limpia(p: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (p or "").upper())


def validar_acceso(patente: str) -> list[dict]:
    """Devuelve una fila por conductor autorizado, o una única fila 'Denegado'."""
    base = {k: None for k in ("patente", "tipo_vehiculo", "marca_modelo", "estado_operativo",
                              "kilometraje_actual", "rut_conductor", "nombre_conductor",
                              "grado_o_cargo", "unidad_destino")}
    veh = next((v for v in tabla("vehiculos").select("*").execute().data
                if _limpia(v["patente"]) == _limpia(patente)), None)
    if not veh:
        return [{**base, "resultado": "Denegado", "motivo": "Patente no registrada en el catálogo"}]
    base.update(patente=veh["patente"], tipo_vehiculo=veh["tipo_vehiculo"], marca_modelo=veh["marca_modelo"],
                estado_operativo=veh["estado_operativo"], kilometraje_actual=veh["kilometraje_actual"])

    auts = tabla("autorizaciones").select("rut_conductor").eq("patente", veh["patente"]).eq("vigente", True).execute().data
    if not auts:
        return [{**base, "resultado": "Denegado", "motivo": "Sin autorización vigente para esta patente"}]

    ruts = [a["rut_conductor"] for a in auts]
    conductores = {c["rut"]: c for c in tabla("conductores").select("*").in_("rut", ruts).execute().data}
    filas = []
    for rut in ruts:
        c = conductores.get(rut)
        fila = {**base, "rut_conductor": rut}
        if c:
            fila.update(nombre_conductor=c["nombre_completo"], grado_o_cargo=c["grado_o_cargo"],
                        unidad_destino=c["unidad_destino"])
        if not c or c["estado"] != "Activo":
            fila.update(resultado="Denegado", motivo=f"Conductor no habilitado ({c['estado'] if c else 'sin registro'})")
        elif veh["estado_operativo"] != "Operativo":
            fila.update(resultado="Alerta de Estado", motivo=f"Vehículo en estado: {veh['estado_operativo']}")
        else:
            fila.update(resultado="Autorizado", motivo="Conductor habilitado y vehículo operativo")
        filas.append(fila)
    return filas


def registrar_evento(patente_consultada: str, resolucion: dict, guardia: str, foto: bytes | None) -> str:
    """Guarda el evento (y la foto) en el bucket. Devuelve la ruta del JSON."""
    ahora = datetime.now(timezone.utc)
    stem = f"accesos/{ahora:%Y-%m-%d}/{ahora:%Y%m%dT%H%M%S}_{patente_consultada}_{uuid.uuid4().hex[:6]}"
    ruta_foto = None
    if foto:
        ruta_foto = f"{stem}.jpg"
        subir_bytes(ruta_foto, comprimir_imagen(foto))
    subir_json(f"{stem}.json", {
        "fecha_hora": ahora.isoformat(),
        "patente_consultada": patente_consultada,
        "patente": resolucion["patente"],
        "rut_conductor": resolucion["rut_conductor"],
        "unidad_destino": resolucion["unidad_destino"],
        "resultado": resolucion["resultado"],
        "motivo": resolucion["motivo"],
        "guardia": guardia,
        "foto": ruta_foto,
    })
    return f"{stem}.json"


def cargar_eventos(desde: date, patente: str | None = None) -> list[dict]:
    """Lee los eventos de la bitácora desde una fecha; opcionalmente de una sola patente."""
    carpetas = [c for c in listar("accesos") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", c) and c >= desde.isoformat()]
    rutas = []
    for c in carpetas:
        for n in listar(f"accesos/{c}"):
            if n.endswith(".json") and (patente is None or f"_{patente}_" in n):
                rutas.append(f"accesos/{c}/{n}")
    with ThreadPoolExecutor(max_workers=8) as ex:
        eventos = [e for e in ex.map(descargar_json, rutas) if e]
    return sorted(eventos, key=lambda e: e["fecha_hora"], reverse=True)
