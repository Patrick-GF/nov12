# Control de Flota — Streamlit + Supabase

Aplicación web/móvil modular en Python con triple perfil (Guardia de Garita, Conductor Operativo,
Administrador de Puesto de Mando), conectada a Supabase (PostgreSQL + Storage).
Usa **solo las 4 tablas del enunciado** (`conductores`, `vehiculos`, `autorizaciones`, `reportes_estado`)
y el bucket `evidencias-vehiculares`; no requiere crear tablas nuevas.

```
.
├── app/
│   ├── main.py            # entrada: login + menú por rol (st.navigation)
│   ├── core/              # auth, db, acceso (validación + bitácora), flota (reglas), placas (OCR), storage
│   └── vistas/            # guardia.py · conductor.py · admin.py
├── sql/00_esquema_base.sql        # script SQL del profesor: crea las 4 tablas y los datos (¡hace DROP!)
├── sql/01_opcional_reglas_en_bd.sql  # opcional: trigger, función y vista equivalentes a la lógica de la app
├── scripts/generar_credenciales.py
├── docs/INFORME_TECNICO.md
├── .streamlit/secrets.toml  # local, ignorado por git (no se sube)
└── app2.py                  # exporta las tablas a CSV/Excel
```

## Puesta en marcha local (VS Code)

1. `python -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
2. Crea `.streamlit/secrets.toml` con este contenido (URL y clave de Supabase entregadas por el profesor):
   ```toml
   [supabase]
   url = "https://TU-PROYECTO.supabase.co"
   key = "TU_SECRET_KEY"
   ```
3. `python scripts/generar_credenciales.py` → agrega los hashes de contraseña a `secrets.toml` y escribe
   `credenciales_iniciales.csv` (usuarios `guardia` y `admin`; los conductores entran con su RUT + clave común).
4. `streamlit run app/main.py`

### Base de datos propia (opcional)

Con el proyecto Supabase del profesor no hace falta ejecutar SQL. Si montas uno propio y vacío: SQL Editor →
ejecuta `sql/00_esquema_base.sql` (crea las 4 tablas con sus 30 conductores, 15 vehículos y 18 autorizaciones) y,
si quieres que la BD también aplique las reglas, `sql/01_opcional_reglas_en_bd.sql`. Crea además el bucket
`evidencias-vehiculares` (límite 800 KB) y cambia URL y clave en `secrets.toml`.

## Despliegue (Streamlit Community Cloud)

Repositorio público en GitHub → *New app* → archivo principal `app/main.py` → en *Settings → Secrets*
pega el contenido completo de tu `secrets.toml`. La cámara del móvil requiere HTTPS (Community Cloud ya lo provee).

## Seguridad — el repositorio es público

- `.streamlit/secrets.toml` y `credenciales_iniciales.csv` están en `.gitignore`: **nunca** los subas.
- La clave `sb_secret_…` da acceso total a la base de datos del proyecto: no la escribas en código, capturas del
  informe ni mensajes públicos.
- Las contraseñas se guardan solo como hash PBKDF2-SHA256 con sal; las imágenes se sirven con URLs firmadas.
