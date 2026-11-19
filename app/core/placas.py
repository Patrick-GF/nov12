"""Utilidades de patentes chilenas (ABCD-12 / AB-1234) y lectura OCR opcional."""
import re
from functools import lru_cache

PATRON_NUEVO = re.compile(r"^([A-Z]{4})(\d{2})$")   # ABCD12
PATRON_ANTIGUO = re.compile(r"^([A-Z]{2})(\d{4})$")  # AB1234


def normalizar_patente(texto: str) -> str:
    limpio = re.sub(r"[^A-Z0-9]", "", (texto or "").upper())
    for patron in (PATRON_NUEVO, PATRON_ANTIGUO):
        m = patron.match(limpio)
        if m:
            return f"{m.group(1)}-{m.group(2)}"
    return limpio


def patente_valida(texto: str) -> bool:
    limpio = re.sub(r"[^A-Z0-9]", "", (texto or "").upper())
    return bool(PATRON_NUEVO.match(limpio) or PATRON_ANTIGUO.match(limpio))


@lru_cache(maxsize=1)
def _lector_ocr():
    import easyocr  # import diferido: es pesado y opcional

    return easyocr.Reader(["en"], gpu=False, verbose=False)


def leer_patente_ocr(imagen_bytes: bytes) -> str | None:
    """Devuelve la primera patente válida detectada en la imagen, o None.

    Si easyocr no está instalado o falla, retorna None y el guardia tipea la patente.
    """
    try:
        import numpy as np
        from PIL import Image
        import io

        img = np.array(Image.open(io.BytesIO(imagen_bytes)).convert("RGB"))
        textos = _lector_ocr().readtext(img, detail=0, allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789- ")
    except Exception:
        return None
    candidatos = [normalizar_patente(t) for t in textos] + [normalizar_patente("".join(textos))]
    for c in candidatos:
        if patente_valida(c):
            return c
    return None
