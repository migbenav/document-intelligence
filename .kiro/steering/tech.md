---
inclusion: auto
---

# Technical Context — Document Intelligence

## Stack tecnológico

### Backend

| Componente | Tecnología | Versión mínima |
|---|---|---|
| Lenguaje | Python | 3.12+ |
| Framework web | FastAPI | 0.100+ |
| Validación/schemas | Pydantic v2 | 2.0+ |
| Abstracción LLM | LiteLLM | latest |
| Parsing PDF | PyMuPDF (fitz) | latest |
| DB client | supabase-py (async) | latest |
| Testing | pytest + httpx | latest |

### Frontend

| Componente | Tecnología | Versión mínima |
|---|---|---|
| Framework | React + TypeScript | React 18+, TS 5+ |
| Build tool | Vite | 5+ |
| Estilos | Tailwind CSS | 3+ |
| Componentes UI | shadcn/ui | latest |
| Visualización relaciones | React Flow | latest |
| Estado | Zustand | latest |
| Testing | Vitest | latest |

### Infraestructura y servicios

| Componente | Tecnología | Tier |
|---|---|---|
| Base de datos | Supabase (PostgreSQL) | Free tier — cloud siempre |
| Storage temporal | Supabase Storage o filesystem del server | Free tier |
| LLM principal | Google Gemini 2.5 Flash | Free tier (500 req/día, 1M tokens/min) |
| LLM secundario | Groq (Llama 3.3 70B) | Free tier (30 req/min) |
| Deploy backend | Render | Free tier |
| Deploy frontend | Vercel | Free tier |
| CI/CD | GitHub Actions | Free (repo público) |
| Contenedores | No se usa Docker | — |

### Estrategia multi-modelo (LLM)

| Tarea | Modelo asignado | Razón |
|---|---|---|
| Extracción completa del Knowledge Model | Gemini 2.5 Flash | Contexto 1M tokens, gratis, calidad alta |
| Inferencia de tipo de documento | Groq Llama 3.3 70B | Tarea simple, velocidad alta |
| Consulta por lenguaje natural (Q&A) | Gemini 2.5 Flash | Mismo contexto, coherente con KM |
| Verificación de evidencia | Groq Llama 3.1 8B | Tarea ligera, alta disponibilidad |
| Fallback general | Groq | Si Gemini tiene rate limit |

Toda comunicación con LLMs pasa por LiteLLM. Cambiar modelo = cambiar config, no código.

## Entorno de desarrollo

- **Local:** Solo código y tests. No Docker, no servicios locales.
- **Base de datos:** Siempre Supabase cloud (free tier). Desarrollo y producción apuntan a la misma tecnología.
- **Backend local:** `uvicorn` o `fastapi dev` apuntando a Supabase cloud.
- **Frontend local:** `npm run dev` apuntando al backend local.
- **Deploy:** Autodeploy desde GitHub (Render para backend, Vercel para frontend).

## Principios arquitectónicos

Derivados de los ADR aprobados. Toda implementación debe respetar estos principios:

### Modelo de conocimiento (ADR-002)

- El Knowledge Model es una colección de elementos tipados con relaciones opcionales.
- Taxonomía fija de 6 tipos: propósito, conceptos, actores, reglas, procesos, restricciones.
- Vocabulario de relaciones fijo de 4 tipos: constrains, participates_in, depends_on, contradicts.
- Cada elemento incluye un `source_ref` flexible (document_id, page, section, chunk_id, evidence).
- Los tipos se representan como strings extensibles, no enums cerrados.

### Ingesta desacoplada (ADR-003)

- La capa de ingesta es un módulo independiente del motor de análisis.
- Transforma cualquier formato soportado a una representación intermedia de texto estructurado.
- El motor de análisis opera sobre la representación intermedia, sin conocimiento del formato original.
- Formatos MVP: Markdown (.md), texto plano (.txt), PDF (.pdf).
- Límites: 1 MB (MD/TXT), 10 MB (PDF). UTF-8 para MD/TXT. Español e inglés.

### Confiabilidad (ADR-004)

- Trust by Evidence: todo resultado es trazable, no se promete precisión absoluta.
- Cada elemento tiene un `source_ref` verificado contra el documento fuente.
- Elementos no-verificables se marcan como tales.
- Reproducibilidad = consistencia estructural entre ejecuciones, no texto idéntico.
- Parámetros de generación controlados (temperatura mínima disponible) y prompts versionados.

### Privacidad (ADR-005)

- El pipeline se comunica con el servicio de IA a través de LiteLLM como capa de abstracción.
- El proveedor de IA es reemplazable sin modificar el pipeline de análisis.
- Consentimiento explícito del usuario antes de enviar datos.
- Solo se envía texto del documento y prompts del sistema. No metadata del usuario, cuentas ni historial.
- Retención del documento original limitada a lo operativamente necesario para la sesión.

### Análisis de calidad (ADR-006)

- 4 tipos de documento: PRD, Technical Spec, Policy/Process, Generic.
- Selección híbrida: inferencia automática + confirmación del usuario.
- Esquemas fijos en MVP; estructura extensible para futuras versiones.
- Generic soporta todas las capacidades excepto evaluación de completitud basada en esquema.

## Restricciones técnicas permanentes

- No acoplar código a un proveedor de IA específico (todo pasa por LiteLLM).
- No enviar metadata de usuario, información de cuenta ni historial al servicio de IA.
- No almacenar el documento original más allá de la sesión operativa.
- No asumir referencias basadas en líneas (los PDFs no tienen líneas estables).
- No implementar Knowledge Graph completo ni motor de grafos.
- No implementar lógica multi-documento.
- No implementar configuración dinámica de taxonomías o tipos de documentos.
- No usar Docker para desarrollo ni despliegue en esta etapa.
- No usar SQLite — la base de datos es Supabase (PostgreSQL) desde el inicio.

## ADRs de referencia

- #[[file:docs/decisions/ADR-001-mvp-scope.md]]
- #[[file:docs/decisions/ADR-002-knowledge-model.md]]
- #[[file:docs/decisions/ADR-003-document-ingestion.md]]
- #[[file:docs/decisions/ADR-004-reliability-trust-model.md]]
- #[[file:docs/decisions/ADR-005-privacy-external-processing.md]]
- #[[file:docs/decisions/ADR-006-document-type-schemas.md]]
- #[[file:docs/architecture/001-technology-stack.md]]
