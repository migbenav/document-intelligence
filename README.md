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
| Backend | Python 3.12+, FastAPI, Pydantic v2, LiteLLM |
| Frontend | React 18, TypeScript 5, Vite, Tailwind CSS, shadcn/ui, Zustand |
| Base de datos | Supabase (PostgreSQL + Storage) |
| LLMs | Gemini 2.5 Flash (principal), Groq Llama 3.3 70B (secundario) |
| Parsing | PyMuPDF (PDF), parsers nativos (MD, TXT) |
| Deploy | Render (backend), Vercel (frontend) |

---

## Estructura del repositorio

```
document-intelligence/
├── src/
│   ├── backend/           # API FastAPI + pipeline de ingesta
│   │   ├── app/
│   │   │   ├── api/v1/    # Endpoints REST
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
└── .env                   # Variables de entorno (no se commitea)
```

---

## Desarrollo local

### Requisitos previos

- Python 3.12+
- Node.js 18+ (para el frontend)
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
SUPABASE_URL=https://tu-proyecto.supabase.co
SUPABASE_SERVICE_ROLE_KEY=tu-service-role-key
DOCUMENT_RETENTION_SECONDS=86400
```

Ver [docs/deployment/supabase-setup.md](docs/deployment/supabase-setup.md) para la configuración de tablas y storage.

### Ejecutar

```bash
# Backend (desde src/backend con venv activado)
uvicorn app.main:create_app --factory --reload --port 8000

# Frontend (desde src/frontend)
npm run dev
```

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

🚧 En desarrollo activo — Feature 1 completada, Features 2-7 pendientes.

| Feature | Estado | Descripción |
|---------|--------|-------------|
| 1. Document Ingestion | ✅ Completada | Upload, validación, parsing (PDF/MD/TXT), detección de idioma, IR, persistencia |
| 2. Application Shell & Upload UI | 🔲 Pendiente | Frontend base con upload, progreso, consentimiento |
| 3. Knowledge Model Extraction | 🔲 Pendiente | Motor de análisis con LLM, extracción del Knowledge Model |
| 4. KM Visualization & Exploration | 🔲 Pendiente | Visualización de elementos y relaciones |
| 5. Document Quality Analysis | 🔲 Pendiente | Inconsistencias, faltantes, sugerencias |
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
