# Document Intelligence

Plataforma de inteligencia documental impulsada por IA que transforma documentos en conocimiento estructurado para comprenderlos, mantenerlos y evolucionarlos.

---

## Qué hace

Document Intelligence analiza documentos y construye un **Knowledge Model** — una representación estructurada del conocimiento contenido en el documento (propósitos, conceptos, actores, reglas, procesos, restricciones y sus relaciones).

Capacidades del MVP:

- Cargar documentos (PDF, Markdown, texto plano)
- Generar un Knowledge Model con elementos tipados y relaciones
- Detectar inconsistencias internas (contradicciones, ambigüedades)
- Identificar información faltante según el tipo de documento
- Generar sugerencias de mejora
- Responder preguntas en lenguaje natural sobre el contenido

---

## Stack tecnológico

| Capa | Tecnologías |
|------|-------------|
| Backend | Python 3.12–3.14, FastAPI, Pydantic v2, LiteLLM |
| Frontend | React 18, TypeScript 5, Vite, Tailwind CSS, shadcn/ui, Zustand |
| Base de datos | Supabase (PostgreSQL + Storage) |
| LLMs | Gemini 2.5 Flash (principal), Groq Llama 3.3 70B (secundario) |
| Parsing | PyMuPDF (PDF), parsers nativos (MD, TXT) |
| Deploy | Render (backend), Vercel (frontend) |

### Versiones exactas verificadas

| Dependencia | Versión | Notas |
|-------------|---------|-------|
| Python | 3.14.2 | Compatible; ver restricción de litellm abajo |
| Node.js | 24.13.0 | — |
| litellm | 1.83.7 | **⚠️ Pinned.** Versiones 1.84–1.92 requieren `<3.14`. La 1.93+ requiere compilar extensiones Rust en Windows. Usar `==1.83.7` hasta que se publique un wheel precompilado. |
| FastAPI | 0.140.0 | — |
| Pydantic | 2.12.5 | Requerida por litellm 1.83.7 (la resuelve automáticamente) |
| supabase-py | 2.31.0 | — |
| PyMuPDF | 1.28.0 | — |
| uvicorn | 0.51.0 | — |
| python-dotenv | 1.0.1 | — |

---

## Estructura del repositorio

```
document-intelligence/
├── src/
│   ├── backend/           # API FastAPI + pipeline de ingesta
│   │   ├── app/
│   │   │   ├── api/v1/    # Endpoints REST
│   │   │   ├── analysis/  # Motor de análisis, quality analysis
│   │   │   ├── ingestion/ # Adapters, validator, IR builder, storage
│   │   │   ├── models/    # Modelos Pydantic del dominio
│   │   │   └── db/        # Migraciones SQL
│   │   └── pyproject.toml
│   ├── frontend/          # React + Vite app
│   │   ├── src/
│   │   └── package.json
│   └── shared/            # Modelos/tipos compartidos (futuro)
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   └── fixtures/
├── docs/
│   ├── architecture/      # Stack, arquitectura, roadmap
│   ├── decisions/         # ADRs (001-006)
│   ├── deployment/        # Guías de setup local y Supabase
│   ├── product/           # Visión, PRD, spec MVP
│   └── methodology/       # Metodología de desarrollo
├── scripts/
├── infrastructure/
├── dev.ps1                # Script para levantar backend + frontend juntos
└── .env                   # Variables de entorno (no se commitea)
```

---

## Desarrollo local

### Requisitos previos

- Python 3.12–3.14 (verificado con 3.14.2)
- Node.js 18+ (verificado con 24.13.0)
- Git 2.30+

### Backend

```bash
cd src/backend
python -m venv .venv

# Activar el entorno virtual
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

# Instalar dependencias
pip install -e ".[dev]"
```

### Frontend

```bash
cd src/frontend
npm install
```

### Variables de entorno

Crear `.env` en la raíz del proyecto:

```env
# Supabase
SUPABASE_URL=https://tu-proyecto.supabase.co
SUPABASE_SERVICE_ROLE_KEY=tu-service-role-key
DOCUMENT_RETENTION_SECONDS=86400

# LLM API Keys (obligatorias para el backend)
GEMINI_API_KEY=tu-api-key-de-google-ai-studio
GROQ_API_KEY=tu-api-key-de-groq

# Opcional
CORS_ORIGINS=http://localhost:5173
```

**Dónde obtener las keys:**
- `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` → [Supabase Dashboard](https://supabase.com/dashboard) → Settings → API
- `GEMINI_API_KEY` → [Google AI Studio](https://aistudio.google.com/apikey)
- `GROQ_API_KEY` → [Groq Console](https://console.groq.com/keys)

Ver [docs/deployment/supabase-setup.md](docs/deployment/supabase-setup.md) para la configuración de tablas y storage.

### Ejecutar

```bash
# Ambos servicios simultáneamente (desde la raíz del proyecto)
.\dev.ps1

# O por separado:

# Backend (desde src/backend)
python -m uvicorn app.run:app --reload --port 8000

# Frontend (desde src/frontend)
npm run dev
```

El script `dev.ps1` levanta backend y frontend en paralelo y los cierra juntos con `Ctrl+C`.

### Tests

```bash
# Desde la raíz del proyecto, con el venv activado
python -m pytest tests/unit -v

# Frontend
cd src/frontend
npm run test
```

---

## Estado del proyecto

🚧 En desarrollo activo — Features 1–5 completadas, Features 6–7 pendientes.

| Feature | Estado | Descripción |
|---------|--------|-------------|
| 1. Document Ingestion | ✅ Completada | Upload, validación, parsing (PDF/MD/TXT), detección de idioma, IR, persistencia |
| 2. Application Shell & Upload UI | ✅ Completada | Frontend shell, upload con drag & drop, progreso, consentimiento, error recovery |
| 3. Knowledge Model Extraction | ✅ Completada | Motor de análisis con LLM, inferencia de tipo, extracción del KM, verificación de evidencia |
| 4. KM Visualization & Exploration | ✅ Completada | Vista de lista/grafo, panel de detalle, evidencia, navegación por teclado, accesibilidad |
| 5. Document Quality Analysis | ✅ Completada | Contradicciones, ambigüedades, completitud, sugerencias con evidencia trazable |
| 6. Natural Language Queries | 🔲 Pendiente | Chat sobre el documento con evidencia trazable |
| 7. User Feedback | 🔲 Pendiente | Marcar elementos como incorrectos/irrelevantes |

---

## API

Base URL: `http://localhost:8000/api/v1/documents`

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/upload` | Cargar un documento para procesamiento |
| GET | `/{id}/status` | Estado del procesamiento |
| GET | `/{id}/ir` | Representación intermedia generada |
| POST | `/{id}/analyze` | Iniciar análisis del documento |
| POST | `/{id}/confirm-type` | Confirmar tipo de documento |
| GET | `/{id}/knowledge-model` | Obtener el Knowledge Model generado |
| POST | `/{id}/quality-analysis` | Iniciar análisis de calidad |
| GET | `/{id}/quality-analysis` | Obtener resultados de calidad |

Documentación interactiva disponible en `http://localhost:8000/docs` (Swagger UI).

---

## Documentación

- [Visión del producto](docs/product/01-product-vision.md)
- [PRD](docs/product/03-prd.md)
- [Stack tecnológico](docs/architecture/001-technology-stack.md)
- [Arquitectura actual](docs/architecture/002-current-system-architecture.md)
- [MVP Roadmap](docs/architecture/mvp-roadmap.md)
- [Setup local](docs/deployment/local-setup.md)
- [Setup Supabase](docs/deployment/supabase-setup.md)
- [ADRs](docs/decisions/)

---

## Licencia

Ver [LICENSE](LICENSE).
