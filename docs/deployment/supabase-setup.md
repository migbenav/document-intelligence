# Supabase Setup — Prerequisitos para el Backend

Este documento describe los pasos de configuración que deben completarse en Supabase y en el entorno local **antes** de ejecutar el backend. Sin estos pasos, la aplicación no podrá conectarse a la base de datos, subir archivos ni gestionar la retención temporal de documentos.

---

## 1. Crear las tablas en la base de datos

**Por qué:** El backend escribe y lee de las tablas `documents`, `document_chunks` y `analysis_sessions`. Sin ellas, cualquier operación de persistencia fallará.

**Cómo:**

1. Abre el **SQL Editor** en Supabase Dashboard.
2. Ejecuta las migraciones **en orden**:

| # | Archivo | Qué crea |
|---|---------|----------|
| 1 | `src/backend/app/db/migrations/001_create_documents.sql` | Tablas `documents` y `document_chunks`, índice `idx_chunks_document` |
| 2 | `src/backend/app/db/migrations/002_create_analysis_sessions.sql` | Tabla `analysis_sessions` (Knowledge Model, estado del análisis) |
| 3 | `src/backend/app/db/migrations/003_add_quality_analysis.sql` | Columnas de quality analysis en `analysis_sessions` |

Copia el contenido de cada archivo SQL y ejecútalo en el SQL Editor.

**Verificación:** En Table Editor confirma que las tres tablas existen (`documents`, `document_chunks`, `analysis_sessions`) y que `analysis_sessions` tiene las columnas `quality_analysis`, `quality_status`, etc.

---

## 2. Crear el bucket de Storage

**Por qué:** El método `store_original` sube el archivo original del usuario a Supabase Storage bajo la ruta `documents/{document_id}/original/{filename}`. Si el bucket no existe, la operación falla.

**Cómo:**

1. Ve a **Storage** en Supabase Dashboard.
2. Crea un nuevo bucket con el nombre: `documents`.
3. Configuración:
   - **Public:** No (el bucket debe ser privado)
   - **File size limit:** 10 MB (coincide con el límite máximo para PDF)
   - **Allowed MIME types:** dejar vacío (sin restricción) o limitar a `text/plain`, `text/markdown`, `application/pdf`

**Verificación:** El bucket `documents` aparece en la lista de Storage y está marcado como privado.

---

## 3. Configurar Row Level Security (RLS)

**Por qué:** Supabase activa RLS por defecto en tablas nuevas. El backend usa la `service_role` key que bypasea RLS, por lo que no se necesitan políticas adicionales para el MVP. Sin embargo, es importante confirmar que no hay políticas restrictivas que bloqueen al service role.

**Acción:**

- Confirma que RLS está **habilitado** en ambas tablas (es el default y es correcto por seguridad).
- **No** crees políticas restrictivas. El service role key bypasea RLS automáticamente.
- Si en el futuro se expone acceso desde el frontend con la `anon` key, se deberán crear políticas específicas.

---

## 4. Crear el archivo `.env`

**Por qué:** El backend necesita credenciales para conectarse a Supabase, keys para los LLMs, y un parámetro configurable para la retención de documentos. Estas variables no se hardcodean en el código (por seguridad y flexibilidad).

**Cómo:**

Crea un archivo `.env` en la raíz del proyecto (`document-intelligence/.env`) con el siguiente contenido:

```env
# Supabase
SUPABASE_URL=https://tu-proyecto.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
DOCUMENT_RETENTION_SECONDS=86400

# LLM API Keys (obligatorias)
GEMINI_API_KEY=tu-api-key-de-google-ai-studio
GROQ_API_KEY=tu-api-key-de-groq

# Opcional
CORS_ORIGINS=http://localhost:5173
```

**Variables:**

| Variable | Valor | Dónde encontrarla |
|---|---|---|
| `SUPABASE_URL` | URL del proyecto | Dashboard → Settings → API → Project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | JWT service_role (secret) | Dashboard → Settings → API → service_role key |
| `GEMINI_API_KEY` | API key de Google AI | [Google AI Studio](https://aistudio.google.com/apikey) |
| `GROQ_API_KEY` | API key de Groq | [Groq Console](https://console.groq.com/keys) |
| `DOCUMENT_RETENTION_SECONDS` | Segundos antes de expirar un documento | Configurable. Default sugerido: `86400` (24 horas) |

**Notas sobre credenciales:**

- Se usa la **service_role key** (formato JWT `eyJhbGciOi...`), no la anon key ni la nueva Secret Key (`sb_secret_...`).
- La service_role key tiene acceso completo y bypasea RLS. No exponerla al frontend.
- Las LLM API keys son obligatorias — sin ellas el backend lanza `ConfigurationError` al arrancar.
- El `.gitignore` del proyecto ya incluye `.env` y `.env.*`, por lo que no se committeará.

---

## 5. Instalar dependencias

**Por qué:** El `StorageService` usa `supabase-py` para interactuar con la base de datos y Storage. Debe estar instalado en el virtualenv.

**Cómo:**

```bash
cd src/backend
pip install -e ".[dev]"
```

Esto instala `supabase>=2.0.0` junto con el resto de dependencias del proyecto.

**Verificación:**

```bash
python -c "import supabase; print(supabase.__version__)"
```

---

## 6. Crear el módulo de configuración (ya implementado)

El código incluye un entrypoint (`src/backend/app/run.py`) que:

| Responsabilidad | Implementación |
|---|---|
| Carga `.env` desde la raíz del proyecto | `python-dotenv` (`load_dotenv`) |
| Inicializa el cliente Supabase | `supabase.create_client(url, key)` |
| Pasa el cliente al app factory | `create_app(supabase_client=...)` |
| Lee CORS origins | Variable `CORS_ORIGINS` (default: `*`) |

No es necesario crear estos módulos manualmente — ya existen.

---

## Checklist de verificación

Antes de ejecutar el backend, confirma:

- [ ] Tablas `documents`, `document_chunks` y `analysis_sessions` creadas en Supabase (3 migraciones)
- [ ] Bucket `documents` creado en Storage (privado, 10 MB límite)
- [ ] Archivo `.env` creado con `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY` y `DOCUMENT_RETENTION_SECONDS`
- [ ] RLS habilitado sin políticas restrictivas
- [ ] Dependencias instaladas (`supabase` y `litellm` disponibles en el entorno Python)

---

## Referencia

- Migraciones SQL: `src/backend/app/db/migrations/001_create_documents.sql`, `002_create_analysis_sessions.sql`, `003_add_quality_analysis.sql`
- Entry point del backend: `src/backend/app/run.py`
- Diseño del StorageService: `.kiro/specs/document-ingestion/design.md` (sección Storage)
- Stack tecnológico: `docs/architecture/001-technology-stack.md`
