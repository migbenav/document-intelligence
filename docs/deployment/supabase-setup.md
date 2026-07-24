# Supabase Setup — Prerequisitos para el Storage Service

Este documento describe los pasos de configuración que deben completarse en Supabase y en el entorno local **antes** de ejecutar el Task 9 (Storage Service) del spec de Document Ingestion.

Sin estos pasos, el `StorageService` no podrá conectarse a la base de datos, subir archivos ni gestionar la retención temporal de documentos.

---

## 1. Crear las tablas en la base de datos

**Por qué:** El `StorageService` escribe y lee de las tablas `documents` y `document_chunks`. Sin ellas, cualquier operación de persistencia fallará.

**Cómo:**

1. Abre el **SQL Editor** en Supabase Dashboard.
2. Copia y ejecuta el contenido de `src/backend/app/db/migrations/001_create_documents.sql`.

Este script crea:

| Tabla | Propósito |
|---|---|
| `documents` | Metadata del documento, estado del pipeline, timestamp de expiración |
| `document_chunks` | Chunks de texto extraídos con contexto estructural, vinculados al documento por FK con CASCADE |

También crea el índice `idx_chunks_document` para consultas por `document_id`.

**Verificación:** En Table Editor confirma que ambas tablas existen y que `document_chunks.document_id` tiene la relación FK con CASCADE configurada.

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

**Por qué:** El backend necesita credenciales para conectarse a Supabase y un parámetro configurable para la retención de documentos. Estas variables no se hardcodean en el código (por seguridad y flexibilidad).

**Cómo:**

Crea un archivo `.env` en la raíz del proyecto (`document-intelligence/.env`) con el siguiente contenido:

```env
SUPABASE_URL=https://tu-proyecto.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
DOCUMENT_RETENTION_SECONDS=86400
```

**Variables:**

| Variable | Valor | Dónde encontrarla |
|---|---|---|
| `SUPABASE_URL` | URL del proyecto | Dashboard → Settings → API → Project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | JWT service_role (secret) | Dashboard → Settings → API → service_role key |
| `DOCUMENT_RETENTION_SECONDS` | Segundos antes de expirar un documento | Configurable. Default sugerido: `86400` (24 horas) |

**Notas sobre credenciales:**

- Se usa la **service_role key** (formato JWT `eyJhbGciOi...`), no la anon key ni la nueva Secret Key (`sb_secret_...`).
- La service_role key tiene acceso completo y bypasea RLS. No exponerla al frontend.
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

## 6. Crear el módulo de configuración (se crea con el Task 9)

**Por qué:** El código necesita un punto centralizado para leer las variables de entorno y exponer el cliente de Supabase al resto del backend.

Esto se implementa como parte del Task 9 e incluye:

| Archivo | Propósito |
|---|---|
| `src/backend/app/config.py` | Lee variables de entorno, expone `Settings` con validación |
| `src/backend/app/db/__init__.py` | Inicializa y expone el cliente `supabase-py` |

No es necesario crearlos manualmente — el Task 9 los genera.

---

## Checklist de verificación

Antes de ejecutar el Task 9, confirma:

- [ ] Tablas `documents` y `document_chunks` creadas en Supabase
- [ ] Bucket `documents` creado en Storage (privado, 10 MB límite)
- [ ] Archivo `.env` creado con `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` y `DOCUMENT_RETENTION_SECONDS`
- [ ] RLS habilitado sin políticas restrictivas
- [ ] Dependencias instaladas (`supabase` disponible en el venv)

---

## Referencia

- Migración SQL: `src/backend/app/db/migrations/001_create_documents.sql`
- Diseño del StorageService: `.kiro/specs/document-ingestion/design.md` (sección Storage)
- Stack tecnológico: `.kiro/steering/tech.md`
