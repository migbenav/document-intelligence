# Local Development Setup

Guía completa para configurar el entorno de desarrollo local del proyecto Document Intelligence. Cada paso indica por qué es necesario y en qué momento del desarrollo se requiere.

---

## Requisitos previos del sistema

Antes de empezar, verifica que tienes instalado:

| Herramienta | Versión | Verificación | Notas |
|---|---|---|---|
| Python | 3.12–3.14 | `python --version` | Verificado con 3.14.2. Ver restricción de litellm abajo. |
| pip | 23+ | `pip --version` | — |
| Git | 2.30+ | `git --version` | — |
| Node.js | 18+ | `node --version` | Verificado con 24.13.0 |

**Por qué Python 3.12–3.14:** El proyecto usa sintaxis moderna y el `pyproject.toml` declara `>=3.12`. Funciona con 3.14, pero `litellm` debe fijarse a `==1.83.7` (ver sección de problemas conocidos al final).

**Por qué Node.js 18+:** El frontend usa Vite, React 18 y las últimas APIs de Node.js.

---

## 1. Clonar el repositorio

```bash
git clone https://github.com/<org>/document-intelligence.git
cd document-intelligence
```

**Cuándo:** Primera vez que trabajas en el proyecto.

---

## 2. Crear el entorno virtual

```bash
cd src/backend
python -m venv .venv
```

**Desde dónde:** `src/backend/` — el entorno virtual vive junto al `pyproject.toml` del backend.

**Por qué un venv:**
- Aísla las dependencias del proyecto de las del sistema.
- Evita conflictos de versiones entre proyectos.
- Asegura que todos los desarrolladores usan las mismas versiones.

**Nota:** El `.gitignore` ya excluye `.venv/`, `venv/` y `env/`.

---

## 3. Activar el entorno virtual

**Windows (PowerShell):**
```powershell
.venv\Scripts\Activate.ps1
```

**Windows (CMD):**
```cmd
.venv\Scripts\activate.bat
```

**Linux/macOS:**
```bash
source .venv/bin/activate
```

**Cuándo:** Cada vez que abras una terminal para trabajar en el proyecto. Kiro/VS Code puede configurarse para activarlo automáticamente.

**Verificación:** El prompt de la terminal muestra `(.venv)` al inicio.

---

## 4. Instalar dependencias

Desde `src/backend/` con el venv activado:

```bash
pip install -e ".[dev]"
```

**Qué instala:**

| Grupo | Paquetes | Versión usada | Propósito |
|---|---|---|---|
| Core | fastapi | 0.140.0 | Framework web async |
| Core | pydantic | 2.12.5 | Validación y schemas |
| Core | pymupdf | 1.28.0 | Parsing de PDFs |
| Core | supabase | 2.31.0 | Cliente de Supabase |
| Core | python-multipart | — | Upload de archivos |
| Core | python-dotenv | 1.0.1 | Carga de .env |
| Core | uvicorn | 0.51.0 | Servidor ASGI |
| Core | litellm | **1.83.7** | Abstracción LLM (⚠️ versión fija) |
| Dev | pytest, pytest-asyncio, httpx, hypothesis | — | Testing |

**⚠️ Restricción de litellm:** Si usas Python 3.14, debes instalar `litellm==1.83.7` explícitamente antes de `pip install -e ".[dev]"`. Las versiones 1.84–1.92 declaran `Requires-Python: <3.14`, y la 1.93+ intenta compilar extensiones Rust que fallan en Windows sin toolchain. Ver sección de Troubleshooting.

**Por qué `-e` (editable):** Instala el paquete en modo editable — los cambios en el código se reflejan inmediatamente sin reinstalar. Ideal para desarrollo.

**Cuándo:** La primera vez, y cada vez que se modifique `pyproject.toml` con nuevas dependencias.

---

## 5. Crear el archivo `.env`

Crea el archivo en la **raíz del proyecto** (`document-intelligence/.env`):

```env
# Supabase (obligatorias para persistencia)
SUPABASE_URL=https://tu-proyecto.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
DOCUMENT_RETENTION_SECONDS=86400

# LLM API Keys (obligatorias para el motor de análisis)
GEMINI_API_KEY=tu-api-key-de-google-ai-studio
GROQ_API_KEY=tu-api-key-de-groq

# Opcional
CORS_ORIGINS=http://localhost:5173
```

**Por qué:**
- El backend necesita credenciales para conectarse a Supabase (DB + Storage).
- Las API keys de Gemini y Groq son obligatorias — sin ellas el backend no arranca (lanza `ConfigurationError` al iniciar).
- La retención de documentos es configurable sin tocar código.
- Las credenciales no se commitean (`.gitignore` incluye `.env`).

**Dónde obtener los valores:**
- `SUPABASE_URL` → Dashboard → Settings → API → Project URL
- `SUPABASE_SERVICE_ROLE_KEY` → Dashboard → Settings → API → service_role key (secret, formato JWT)
- `GEMINI_API_KEY` → [Google AI Studio](https://aistudio.google.com/apikey)
- `GROQ_API_KEY` → [Groq Console](https://console.groq.com/keys)
- `DOCUMENT_RETENTION_SECONDS` → Default sugerido: `86400` (24 horas)

**Cuándo:** Antes de ejecutar el backend. Sin las variables de Supabase los servicios de persistencia no se activan. Sin las keys de LLM el backend falla al intentar crear el `LLMClient`.

---

## 6. Configurar Supabase

Este paso se documenta en detalle en [supabase-setup.md](./supabase-setup.md). Resumen:

1. Ejecutar las **3 migraciones SQL** en orden en el SQL Editor de Supabase:
   - `001_create_documents.sql` — tablas `documents` y `document_chunks`
   - `002_create_analysis_sessions.sql` — tabla `analysis_sessions`
   - `003_add_quality_analysis.sql` — columnas de quality analysis
2. Crear el bucket `documents` en Storage (privado, 10 MB límite).
3. Verificar que RLS está habilitado sin políticas restrictivas.

**Cuándo:** Antes de usar la aplicación. Sin las tablas, cualquier operación de persistencia falla.

---

## 7. Frontend — Instalar dependencias

```bash
cd src/frontend
npm install
```

**Desde dónde:** `src/frontend/` — el proyecto React/Vite con su `package.json`.

**Qué instala:**

| Grupo | Paquetes principales | Propósito |
|---|---|---|
| Core | react, react-dom, zustand, reactflow, @dagrejs/dagre, tailwindcss | Runtime del frontend |
| UI | @radix-ui/*, class-variance-authority, lucide-react, tailwind-merge | Componentes y estilos |
| Dev | vite, typescript, vitest, @testing-library/react, fast-check, jest-axe | Build, tipos, testing |

**Cuándo:** La primera vez, y cada vez que se modifique `package.json` con nuevas dependencias.

---

## 8. Frontend — Ejecutar tests

Desde `src/frontend/`:

```bash
npm test
```

**Qué esperar:** 382 tests pasando en 31 archivos de test (store, components, properties, accessibility, integration).

---

## 9. Frontend — Servidor de desarrollo

Desde `src/frontend/`:

```bash
npm run dev
```

**Puerto:** http://localhost:5173 por defecto (Vite).

**Requiere:** El backend corriendo en puerto 8000 para las llamadas API. La variable `VITE_API_BASE_URL` en `.env` del frontend (o el default http://localhost:8000) configura la conexión.

**Cuándo:** Para desarrollo visual y pruebas manuales del flujo completo.

---

## 10. Verificar la instalación

Desde la raíz del proyecto (`document-intelligence/`), con el venv activado:

```bash
python -m pytest tests/unit -v
```

**Por qué desde la raíz:** El `conftest.py` en `tests/` agrega `src/backend` al `sys.path`, permitiendo que los tests importen `app.*` directamente.

**Qué esperar:** Todos los unit tests de tasks completados (1-8) deben pasar sin errores.

---

## 11. Ejecutar el backend (desarrollo)

Desde `src/backend/`:

```bash
python -m uvicorn app.run:app --reload --port 8000
```

**Nota:** Se usa `app.run:app` (no `app.main:create_app --factory`). El módulo `run.py` carga el `.env`, inicializa el cliente Supabase y pasa las dependencias al factory.

**Por qué `--reload`:** Recarga automáticamente al detectar cambios en el código. Solo para desarrollo.

---

## 12. Ejecutar ambos servicios juntos

Desde la raíz del proyecto:

```powershell
.\dev.ps1
```

Este script PowerShell levanta backend (puerto 8000) y frontend (puerto 5173) simultáneamente. `Ctrl+C` cierra ambos procesos.

**Cuándo:** Para desarrollo y pruebas del flujo end-to-end.

---

## Estructura de directorios relevante

```
document-intelligence/
├── .env                          ← Credenciales (no se commitea)
├── dev.ps1                       ← Script para levantar ambos servicios
├── src/
│   └── backend/
│       ├── .venv/                ← Entorno virtual (no se commitea)
│       ├── pyproject.toml        ← Dependencias y config del proyecto
│       └── app/                  ← Código fuente del backend
│           ├── run.py            ← Entry point (carga .env, inicia Supabase)
│           └── main.py           ← App factory (dependency injection)
└── tests/
    ├── conftest.py               ← Configura sys.path para imports
    ├── unit/                     ← Tests unitarios
    ├── integration/              ← Tests de integración
    └── fixtures/                 ← Archivos de prueba
```

---

## Orden de necesidad por paso

| Paso | Requerido para |
|---|---|
| Python venv + dependencias | Cualquier desarrollo backend |
| Node.js + npm install | Cualquier desarrollo frontend |
| Archivo `.env` (Supabase) | Backend: persistencia de documentos |
| Archivo `.env` (LLM keys) | Backend: motor de análisis (Feature 3+) |
| Tablas en Supabase (3 migraciones) | Backend: operaciones de persistencia |
| Bucket en Supabase Storage | Backend: almacenamiento de archivos originales |
| Ejecutar el backend (`uvicorn`) | Pruebas end-to-end, uso real del frontend |
| Ejecutar el frontend (`npm run dev`) | Pruebas end-to-end, uso real |
| `.\dev.ps1` | Alternativa para levantar ambos juntos |

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'app'`

**Causa:** El venv no está activado, o las dependencias no se instalaron con `-e`.

**Solución:**
```bash
cd src/backend
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

### `litellm` no se instala (error de Rust/compilación)

**Causa:** Estás usando Python 3.14 y pip resuelve litellm >= 1.93.0, que intenta compilar extensiones Rust.

**Solución:** Instalar la versión pinneada primero:
```bash
pip install "litellm==1.83.7"
pip install -e ".[dev]"
```

### `ConfigurationError: Missing required LLM API keys`

**Causa:** Faltan `GEMINI_API_KEY` y/o `GROQ_API_KEY` en el archivo `.env`.

**Solución:** Agregar ambas keys al `.env` en la raíz del proyecto. El backend las valida al arrancar.

### `RuntimeError: Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY`

**Causa:** El archivo `.env` no tiene las credenciales de Supabase o no se está cargando correctamente.

**Solución:** Verificar que `.env` existe en la raíz del proyecto con `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY` definidos.

### "Network error during upload" en el frontend

**Causa:** El backend no está corriendo, o no tiene el cliente Supabase inicializado.

**Solución:** Verificar que el backend está corriendo en puerto 8000 con `python -m uvicorn app.run:app --reload --port 8000` (no con `app.main:create_app --factory`).

### Tests no encuentran los módulos

**Causa:** Estás ejecutando pytest desde `src/backend/` en vez de la raíz.

**Solución:** Ejecuta siempre desde la raíz del proyecto:
```bash
cd document-intelligence
python -m pytest tests/unit -v
```

### `supabase` import falla

**Causa:** El paquete no está instalado o el venv no está activado.

**Solución:**
```bash
pip install -e ".[dev]"
python -c "import supabase; print(supabase.__version__)"
```

### Frontend `npm test` falla con módulos no encontrados

**Causa:** Las dependencias no se instalaron correctamente.

**Solución:**
```bash
cd src/frontend
rm -rf node_modules
npm install
npm test
```

### React Flow tests fallan en CI

**Causa:** React Flow requiere medidas DOM no disponibles en jsdom.

**Solución:** Los tests de RelationshipGraphView mockean React Flow. Verificar que el mock está en su lugar en el archivo de test.

---

## Referencias

- [Supabase Setup](./supabase-setup.md) — Configuración detallada de tablas, bucket y RLS
- Stack tecnológico: `.kiro/steering/tech.md`
- Estructura del repositorio: `.kiro/steering/structure.md`
