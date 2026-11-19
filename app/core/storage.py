"""Supabase Storage: bucket privado 'evidencias-vehiculares' (máx. 800 KB por imagen)."""
import io
import json
import uuid
from datetime import datetime, timezone

from PIL import Image, ImageOps

from core.db import get_client

BUCKET = "evidencias-vehiculares"
MAX_BYTES = 800 * 1024


def comprimir_imagen(datos: bytes, max_bytes: int = MAX_BYTES) -> bytes:
    """Reescala y recomprime a JPEG hasta quedar bajo el límite del bucket."""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(datos))).convert("RGB")
    lado, calidad = 1600, 85
    while True:
        copia = img.copy()
        copia.thumbnail((lado, lado))
        buf = io.BytesIO()
        copia.save(buf, "JPEG", quality=calidad, optimize=True)
        if buf.tell() <= max_bytes or (lado <= 320 and calidad <= 40):
            return buf.getvalue()
        if calidad > 55:
            calidad -= 10
        else:
            lado = int(lado * 0.8)


def subir_evidencia(carpeta: str, clave: str, datos: bytes) -> str:
    """Sube la imagen comprimida y devuelve su ruta dentro del bucket.

    carpeta: 'patentes' u 'odometros'; clave: p. ej. la patente.
    """
    jpeg = comprimir_imagen(datos)
    marca = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    ruta = f"{carpeta}/{clave}/{marca}_{uuid.uuid4().hex[:8]}.jpg"
    get_client().storage.from_(BUCKET).upload(ruta, jpeg, {"content-type": "image/jpeg"})
    return ruta


def url_firmada(ruta: str | None, segundos: int = 3600) -> str | None:
    if not ruta:
        return None
    try:
        return get_client().storage.from_(BUCKET).create_signed_url(ruta, segundos)["signedURL"]
    except Exception:
        return None


# --- Bitácora de accesos como objetos JSON en el bucket (no requiere tablas nuevas) ---
def subir_json(ruta: str, objeto: dict) -> None:
    datos = json.dumps(objeto, ensure_ascii=False).encode("utf-8")
    get_client().storage.from_(BUCKET).upload(ruta, datos, {"content-type": "application/json"})


def subir_bytes(ruta: str, datos: bytes, content_type: str = "image/jpeg") -> None:
    get_client().storage.from_(BUCKET).upload(ruta, datos, {"content-type": content_type})


def listar(carpeta: str, limite: int = 1000) -> list[str]:
    items = get_client().storage.from_(BUCKET).list(carpeta, {"limit": limite})
    return [i["name"] for i in items]


def descargar_json(ruta: str) -> dict | None:
    try:
        return json.loads(get_client().storage.from_(BUCKET).download(ruta))
    except Exception:
        return None
