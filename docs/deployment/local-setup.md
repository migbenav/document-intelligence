# Local Development Setup

Guía completa para configurar el entorno de desarrollo local del proyecto Document Intelligence. Cada paso indica por qué es necesario y en qué momento del desarrollo se requiere.

---

## Requisitos previos del sistema

Antes de empezar, verifica que tienes instalado:

| Herramienta | Versión mínima | Verificación |
|---|---|---|
| Python | 3.12+ | `python --version` |
| pip | 23+ | `pip --version` |
| Git | 2.30+ | `git --version` |

**Por qué Python 3.12+:** El proyecto usa sintaxis moderna (`type` statements, mejorado `match`, performance improvements) y el `pyproject.toml` lo declara como requisito.

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

| Grupo | Paquetes | Propósito |
|---|---|---|
| Core | fastapi, pydantic, pymupdf, supabase, python-multipart, uvicorn, litellm | Runtime del backend |
| Dev | pytest, pytest-asyncio, httpx | Testing |

**Por qué `-e` (editable):** Instala el paquete en modo editable — los cambios en el código se reflejan inmediatamente sin reinstalar. Ideal para desarrollo.

**Cuándo:** La primera vez, y cada vez que se modifique `pyproject.toml` con nuevas dependencias.

---

## 5. Crear el archivo `.env`

Crea el archivo en la **raíz del proyecto** (`document-intelligence/.env`):

```env
SUPABASE_URL=https://tu-proyecto.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
DOCUMENT_RETENTION_SECONDS=86400
```

**Por qué:**
- El backend necesita credenciales para conectarse a Supabase (DB + Storage).
- La retención de documentos es configurable sin tocar código.
- Las credenciales no se commitean (`.gitignore` incluye `.env`).

**Dónde obtener los valores:**
- `SUPABASE_URL` → Dashboard → Settings → API → Project URL
- `SUPABASE_SERVICE_ROLE_KEY` → Dashboard → Settings → API → service_role key (secret, formato JWT)
- `DOCUMENT_RETENTION_SECONDS` → Default sugerido: `86400` (24 horas)

**Cuándo:** Antes de ejecutar el Task 9 (Storage Service). Los tasks 1-8 no requieren conexión a Supabase.

---

## 6. Configurar Supabase

Este paso se documenta en detalle en [supabase-setup.md](./supabase-setup.md). Resumen:

1. Ejecutar la migración SQL para crear tablas (`documents`, `document_chunks`).
2. Crear el bucket `documents` en Storage (privado, 10 MB límite).
3. Verificar que RLS está habilitado sin políticas restrictivas.

**Cuándo:** Antes del Task 9. Los tasks 1-8 son puramente lógica local sin dependencia de Supabase.

---

## 7. Verificar la instalación

Desde la raíz del proyecto (`document-intelligence/`), con el venv activado:

```bash
python -m pytest tests/unit -v
```

**Por qué desde la raíz:** El `conftest.py` en `tests/` agrega `src/backend` al `sys.path`, permitiendo que los tests importen `app.*` directamente.

**Qué esperar:** Todos los unit tests de tasks completados (1-8) deben pasar sin errores.

---

## 8. Ejecutar el backend (desarrollo)

Desde `src/backend/` con el venv activado:

```bash
uvicorn app.main:create_app --factory --reload --port 8000
```

O con FastAPI CLI:

```bash
fastapi dev app/main.py --port 8000
```

**Por qué `--reload`:** Recarga automáticamente al detectar cambios en el código. Solo para desarrollo.

**Cuándo:** A partir del Task 11 (API endpoints). Antes de eso, la funcionalidad se verifica con tests.

---

## Estructura de directorios relevante

```
document-intelligence/
├── .env                          ← Credenciales (no se commitea)
├── src/
│   └── backend/
│       ├── .venv/                ← Entorno virtual (no se commitea)
│       ├── pyproject.toml        ← Dependencias y config del proyecto
│       └── app/                  ← Código fuente del backend
└── tests/
    ├── conftest.py               ← Configura sys.path para imports
    ├── unit/                     ← Tests unitarios
    ├── integration/              ← Tests de integración
    └── fixtures/                 ← Archivos de prueba
```

---

## Orden de necesidad por task

| Paso | Requerido a partir de |
|---|---|
| Entorno virtual + dependencias | Task 1 (cualquier desarrollo) |
| Archivo `.env` | Task 9 (Storage Service) |
| Tablas en Supabase | Task 9 (Storage Service) |
| Bucket en Supabase Storage | Task 9 (Storage Service) |
| Ejecutar el backend (`uvicorn`) | Task 11 (API endpoints) |

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

---

## Referencias

- [Supabase Setup](./supabase-setup.md) — Configuración detallada de tablas, bucket y RLS
- Stack tecnológico: `.kiro/steering/tech.md`
- Estructura del repositorio: `.kiro/steering/structure.md`
