"""Genera las contraseñas de la app y agrega su HASH a .streamlit/secrets.toml.

Uso (raíz del repo):  python scripts/generar_credenciales.py
 - Crea contraseñas aleatorias para: guardia, admin y la clave común de conductores.
 - Escribe solo los hashes PBKDF2 en secrets.toml (sección [auth]).
 - Guarda las contraseñas en texto en credenciales_iniciales.csv (ignorado por git).
No requiere tablas nuevas en Supabase.
"""
import csv
import secrets
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "app"))

from core.auth import hash_password  # noqa: E402

SECRETS = RAIZ / ".streamlit" / "secrets.toml"


def main() -> None:
    texto = SECRETS.read_text(encoding="utf-8")
    if "[auth" in texto:
        sys.exit("secrets.toml ya tiene una sección [auth]. Bórrala si quieres regenerar las credenciales.")

    cuentas = [
        ("guardia", "Guardia de Garita"),
        ("admin", "Administrador Puesto de Mando"),
        ("conductores", "Clave común de conductores (usuario = RUT)"),
    ]
    bloques, filas = [], []
    for clave, descripcion in cuentas:
        pwd = secrets.token_urlsafe(9)
        nombre = f'nombre = "{descripcion}"\n' if clave != "conductores" else ""
        bloques.append(f'[auth.{clave}]\n{nombre}password_hash = "{hash_password(pwd)}"\n')
        filas.append({"usuario": clave if clave != "conductores" else "<RUT del conductor>",
                      "descripcion": descripcion, "contraseña": pwd})

    SECRETS.write_text(texto.rstrip() + "\n\n" + "\n".join(bloques), encoding="utf-8")
    destino = RAIZ / "credenciales_iniciales.csv"
    with destino.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["usuario", "descripcion", "contraseña"])
        w.writeheader()
        w.writerows(filas)
    print(f"Hashes agregados a {SECRETS.name}. Contraseñas en: {destino}")


if __name__ == "__main__":
    main()
