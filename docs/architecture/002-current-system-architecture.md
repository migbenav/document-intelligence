# 002 — Arquitectura actual del sistema

> Fecha: 2026-07-24
> Estado de la implementación: Feature 1 (Document Ingestion) completada
> Próxima feature pendiente: Knowledge Model Extraction (Analysis Engine)

---

## Propósito de este documento

Este documento describe la arquitectura implementada hasta la fecha, clasificando cada archivo y módulo del proyecto por su responsabilidad, interacciones y relación con los requisitos aprobados. Su objetivo es que un desarrollador nuevo pueda comprender rápidamente la estructura, localizar dónde realizar cambios y anticipar el impacto de una modificación.

---

## Vista general del sistema

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Document Intelligence                          │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌─────────────┐     ┌──────────────────────────────────────────┐    │
│  │   Frontend   │────▶│              Backend (FastAPI)            │    │
│  │  (pendiente) │◀────│                                          │    │
│  └─────────────┘     │  ┌──────────┐   ┌────────────────────┐   │    │
│                       │  │ API v1   │──▶│  Ingestion Service  │   │    │
│                       │  └──────────┘   │  (orquestador)      │   │    │
│                       │                 └────────────────────┘   │    │
│                       │                     │ │ │ │ │            │    │
│                       │          ┌──────────┘ │ │ │ └────────┐  │    │
│                       │          ▼            ▼ │ ▼            ▼  │    │
│                       │  ┌──────────┐ ┌──────┐│┌────────┐┌──────┐│    │
│                       │  │Validator │ │Adapt.│││Lang Det.││IR Bld││    │
│                       │  └──────────┘ └──────┘│└────────┘└──────┘│    │
│                       │                       ▼                   │    │
│                       │               ┌──────────────┐            │    │
│                       │               │   Storage    │            │    │
│                       │               │   Service    │            │    │
│                       │               └──────┬───────┘            │    │
│                       └──────────────────────┼───────────────────┘    │
│                                              ▼                        │
│                                    ┌──────────────────┐               │
│                                    │    Supabase      │               │
│                                    │ (PostgreSQL +    │               │
│                                    │  Storage)        │               │
│                                    └──────────────────┘               │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Módulos del backend

### 1. Capa de entrada — API HTTP

| Archivo | Responsabilidad |
|---------|----------------|
| `src/backend/app/main.py` | Application factory: crea la instancia FastAPI, configura CORS, inyecta dependencias y registra routers. |
| `src/backend/app/api/v1/documents.py` | Router con los endpoints de la feature de ingesta: `POST /upload`, `GET /{id}/status`, `GET /{id}/ir`. |
| `src/backend/app/api/__init__.py` | Paquete vacío. |
| `src/backend/app/api/v1/__init__.py` | Paquete vacío. |

**Interacciones:**
- `main.py` instancia `IngestionService` y `StorageService` y los inyecta como dependencias de FastAPI.
- `documents.py` recibe peticiones HTTP, delega en `IngestionService` (upload) o `StorageService` (status, IR), y transforma los resultados en respuestas HTTP con los códigos apropiados (202, 400, 404, 409, 422).

**Dependientes:**
- El frontend (cuando exista) consumirá estos endpoints.
- Los tests de integración ejercitan esta capa mediante `httpx.AsyncClient`.

**Cuándo modificar:**
- Agregar nuevos endpoints (ej. iniciar análisis, obtener Knowledge Model).
- Cambiar códigos de respuesta o formato de errores.
- Agregar middleware (autenticación, rate limiting).

**Impacto de un cambio:**
- Cambios en la interfaz HTTP afectan al frontend y a los tests de integración.
- Cambios en la inyección de dependencias en `main.py` afectan el arranque de toda la aplicación.

**Relación con la spec:**
- Requirements 1 (Upload API), 6 (Feedback/Status) → `documents.py`
- Design: sección "API Design" → contratos de request/response

---

### 2. Modelos de dominio

| Archivo | Responsabilidad |
|---------|----------------|
| `src/backend/app/models/document.py` | Define todos los modelos Pydantic v2 del dominio de ingesta: enums (`DocumentFormat`, `DetectedLanguage`), la representación intermedia (`IntermediateRepresentation`, `DocumentMetadata`, `ContentChunkModel`), modelos de respuesta (`DocumentStatus`, `ValidationErrorResponse`). |

**Interacciones:**
- Consumido por todos los módulos del pipeline de ingesta (validator, adapters, language detector, IR builder, storage, service, API).
- Define el **contrato** entre la capa de ingesta y el futuro motor de análisis.

**Dependientes:**
- Todo el backend depende de estos modelos.
- El motor de análisis (próxima feature) consumirá `IntermediateRepresentation` como input.

**Cuándo modificar:**
- Agregar campos al IR (ej. `source_ref` cuando se implemente el análisis).
- Agregar nuevos formatos al enum `DocumentFormat`.
- Cambiar la estructura de los chunks o metadata.

**Impacto de un cambio:**
- Alto. Un cambio en los modelos puede romper la serialización a DB, las respuestas de la API, y los tests.
- Cambios en `IntermediateRepresentation` afectan el contrato con el motor de análisis.

**Relación con la spec:**
- Requirements 3 (IR Generation), 7 (Format-Independent Processing) → estructura del IR
- Design: sección "Data Models" → definición formal de los Pydantic models

---

### 3. Pipeline de ingesta

#### 3.1 Orquestador

| Archivo | Responsabilidad |
|---------|----------------|
| `src/backend/app/ingestion/service.py` | `IngestionService` — Orquesta el pipeline completo: UUID → validate → create record → store → extract → detect language → build IR → persist. |

**Interacciones:**
- Recibe dependencias por constructor: `Validator`, lista de `FormatAdapter`, `LanguageDetector`, `IRBuilder`, `StorageService`.
- Invocado por `documents.py` (endpoint de upload).
- Coordina todos los módulos del pipeline en secuencia.

**Dependientes:**
- `documents.py` (lo consume).
- Los tests unitarios y de integración lo ejercitan directamente.

**Cuándo modificar:**
- Agregar un paso al pipeline (ej. notificaciones, hooks post-ingesta).
- Cambiar la lógica de manejo de errores.
- Agregar el paso de consentimiento o selección de tipo de documento.

**Impacto de un cambio:**
- Medio-alto. Es el punto central del flujo; un error aquí afecta toda la ingesta.
- No afecta módulos individuales (están desacoplados por interfaz).

**Relación con la spec:**
- Requirements 1, 6, 7 → orquestación del flujo completo
- Design: sección "Interaction Flow" → diagrama de secuencia

---

#### 3.2 Validación

| Archivo | Responsabilidad |
|---------|----------------|
| `src/backend/app/ingestion/validator.py` | `Validator` — Verifica formato (extensión), tamaño (1 MB text, 10 MB PDF) y encoding (UTF-8 para .md/.txt). Retorna `ValidationResult` con error codes específicos. |

**Interacciones:**
- Consumido por `IngestionService` como primer paso del pipeline.
- Usa constantes internas (`_EXTENSION_MAP`, `_MAX_SIZE_TEXT`, `_MAX_SIZE_PDF`).
- Importa `DocumentFormat` de models.

**Dependientes:**
- `IngestionService` (lo invoca).
- `documents.py` (usa los error codes para determinar HTTP status).

**Cuándo modificar:**
- Agregar un nuevo formato soportado (ej. DOCX en el futuro).
- Cambiar límites de tamaño.
- Agregar validaciones adicionales (ej. detección de archivos cifrados).

**Impacto de un cambio:**
- Bajo-medio. Cambios en los límites solo afectan el comportamiento de rechazo.
- Agregar un formato requiere también crear un adapter correspondiente.

**Relación con la spec:**
- Requirements 1.4, 1.5, 1.6, 1.7 → validación de formato, tamaño, encoding
- ADR-003 → restricciones aprobadas

---

#### 3.3 Adaptadores de extracción

| Archivo | Responsabilidad |
|---------|----------------|
| `src/backend/app/ingestion/adapters/base.py` | Define el contrato `FormatAdapter` (ABC) con métodos `can_handle` y `extract`. Define dataclasses compartidas: `ContentChunk`, `ExtractionResult`. |
| `src/backend/app/ingestion/adapters/markdown_adapter.py` | `MarkdownAdapter` — Extrae texto de .md dividiendo por headings h1/h2. Un chunk por sección. |
| `src/backend/app/ingestion/adapters/plaintext_adapter.py` | `PlainTextAdapter` — Extrae texto de .txt detectando headings (ALL CAPS o líneas con underline ===/ ---). |
| `src/backend/app/ingestion/adapters/pdf_adapter.py` | `PdfAdapter` — Extrae texto de PDF con PyMuPDF. Detecta PDFs escaneados, divide páginas largas, maneja tablas. |
| `src/backend/app/ingestion/adapters/__init__.py` | Paquete vacío. |

**Interacciones:**
- `IngestionService` selecciona el adapter apropiado y llama a `extract()`.
- Cada adapter produce `ExtractionResult` (lista de `ContentChunk` + warnings).
- `PdfAdapter` depende de la librería externa `PyMuPDF (fitz)`.

**Dependientes:**
- `IngestionService` (los consume a través de la interfaz `FormatAdapter`).
- Los tests unitarios verifican cada adapter de forma aislada.

**Cuándo modificar:**
- **base.py**: Solo si cambia el contrato (agregar métodos o campos a los dataclasses).
- **Adapters individuales**: Para corregir extracción, mejorar chunking, o ajustar heurísticas.
- **Agregar formato**: Crear un nuevo archivo que implemente `FormatAdapter` y registrarlo en `main.py`.

**Impacto de un cambio:**
- Cambios en `base.py` afectan todos los adapters.
- Cambios en un adapter individual solo afectan documentos de ese formato.
- Un cambio en la estrategia de chunking afecta la calidad del IR y por tanto del análisis posterior.

**Relación con la spec:**
- Requirements 2 (Text Extraction) → cada adapter
- Requirements 7 (Format-Independent Processing) → `FormatAdapter` ABC
- Design: sección "Adapter Pattern for Extraction"
- ADR-003 → principio de ingesta desacoplada

---

#### 3.4 Detección de idioma

| Archivo | Responsabilidad |
|---------|----------------|
| `src/backend/app/ingestion/language.py` | `LanguageDetector` — Clasifica texto como español, inglés o desconocido usando frecuencia de stopwords y patrones de caracteres. Sin dependencias externas ni red. |

**Interacciones:**
- Consumido por `IngestionService` después de la extracción.
- Recibe una muestra de texto (primeros 1000 caracteres del contenido concatenado).
- Retorna `DetectedLanguage` enum.

**Dependientes:**
- `IngestionService` (lo invoca).
- El resultado se almacena en `DocumentMetadata.language`.

**Cuándo modificar:**
- Agregar soporte para nuevos idiomas.
- Ajustar umbrales de confianza.
- Reemplazar por una librería externa si la precisión es insuficiente.

**Impacto de un cambio:**
- Bajo. El idioma es metadata informativa; un error no bloquea el pipeline.
- El motor de análisis futuro usará el idioma para seleccionar prompts en el idioma correcto.

**Relación con la spec:**
- Requirements 4 (Language Detection) → detección es/en/unknown
- ADR-003 → idiomas soportados: español e inglés

---

#### 3.5 Construcción del IR

| Archivo | Responsabilidad |
|---------|----------------|
| `src/backend/app/ingestion/ir_builder.py` | `IRBuilder` — Ensambla la `IntermediateRepresentation` a partir de metadata y chunks. Valida ordering secuencial y unicidad de chunk_ids. |

**Interacciones:**
- Consumido por `IngestionService` después de la detección de idioma.
- Recibe `document_id`, `DocumentMetadata`, lista de `ContentChunkModel`.
- Produce `IntermediateRepresentation` validada.

**Dependientes:**
- `IngestionService` (lo invoca).
- `StorageService.persist_ir()` recibe el IR producido.

**Cuándo modificar:**
- Agregar validaciones adicionales al IR.
- Agregar transformaciones post-extracción (ej. normalización de texto, deduplicación).

**Impacto de un cambio:**
- Bajo. Es un módulo de ensamblaje con validación; cambios afectan solo la integridad del IR.
- Un error en las validaciones puede causar falsos rechazos.

**Relación con la spec:**
- Requirements 3 (IR Generation) → propiedades de correctitud
- Design: "Correctness Properties" → Property 2 (Structural Preservation), Property 3 (Chunk Completeness)

---

#### 3.6 Persistencia

| Archivo | Responsabilidad |
|---------|----------------|
| `src/backend/app/ingestion/storage.py` | `StorageService` — Gestiona la persistencia en Supabase: almacena archivos originales en Storage, crea/actualiza registros en PostgreSQL, recupera status e IR, elimina documentos expirados. |

**Interacciones:**
- Recibe un `supabase_client` en el constructor.
- Invocado por `IngestionService` (store_original, create_document_record, persist_ir, mark_failed).
- Invocado por `documents.py` (get_status, get_ir).
- Interactúa directamente con Supabase (tablas `documents`, `document_chunks` y bucket `documents`).

**Dependientes:**
- `IngestionService` y `documents.py` lo consumen.
- La base de datos Supabase es su recurso externo.
- El job de limpieza (futuro) usará `delete_expired()`.

**Cuándo modificar:**
- Cambiar la estrategia de retención o expiración.
- Agregar nuevas tablas (ej. `knowledge_elements`, `analysis_sessions`).
- Optimizar queries o agregar paginación.
- Implementar el cleanup como cron job.

**Impacto de un cambio:**
- Alto. Es la capa de acceso a datos; errores aquí causan pérdida de datos o corrupción.
- Cambios en el schema de respuesta de Supabase requieren actualizar los mappings.

**Relación con la spec:**
- Requirements 5 (Temporary Storage and Privacy) → retención, expiración, no-metadata
- Design: sección "Components and Interfaces" → StorageService contract
- ADR-005 → principios de privacidad (retención limitada, no user metadata)

---

### 4. Base de datos

| Archivo | Responsabilidad |
|---------|----------------|
| `src/backend/app/db/migrations/001_create_documents.sql` | Migración SQL que crea las tablas `documents` y `document_chunks` con sus constraints, índices y relaciones (FK CASCADE). |
| `src/backend/app/db/__init__.py` | Paquete vacío. |

**Interacciones:**
- Se ejecuta contra Supabase PostgreSQL para crear el schema.
- `StorageService` opera sobre estas tablas.

**Dependientes:**
- Todo el pipeline de persistencia depende de este schema.

**Cuándo modificar:**
- Crear nuevas migraciones (no modificar la existente) para agregar tablas o columnas.
- Ej. tabla `knowledge_elements` para el motor de análisis.
- Ej. tabla `analysis_sessions` para el flujo completo.

**Impacto de un cambio:**
- Crítico. Cambios en el schema de DB requieren migraciones coordinadas con el código.
- Las migraciones deben ser aditivas (no destructivas) para datos existentes.

**Relación con la spec:**
- Design: sección "Database Schema" → definición de tablas
- Requirements 3 (IR almacenado), 5 (retención temporal)

---

### 5. Configuración del proyecto

| Archivo | Responsabilidad |
|---------|----------------|
| `src/backend/pyproject.toml` | Metadatos del proyecto, dependencias de producción (fastapi, pydantic, pymupdf, supabase, python-multipart, uvicorn, litellm) y de desarrollo (pytest, pytest-asyncio, httpx). |
| `.env` | Variables de entorno (credenciales Supabase, configuración). No versionado en contenido. |

**Cuándo modificar:**
- Agregar/actualizar dependencias.
- Cambiar versión mínima de Python.
- Agregar scripts de proyecto.

**Impacto de un cambio:**
- Agregar dependencias puede romper el entorno de desarrollo si hay conflictos.
- `litellm` está declarada pero no usada aún (será consumida por el motor de análisis).

---

## Documentación del proyecto

### Documentación de producto

| Archivo | Propósito |
|---------|-----------|
| `docs/product/01-product-vision.md` | Visión a largo plazo del producto. |
| `docs/product/02-problem-discovery.md` | Investigación del problema e hipótesis a validar. |
| `docs/product/03-prd.md` | Product Requirements Document — capacidades C1-C7, flujo del usuario, priorización MoSCoW. |
| `docs/product/04-product-mvp-specification.md` | Especificación funcional detallada del MVP: US, RF, RNF, criterios de aceptación. |

**Cuándo consultar:** Al definir nuevas features o validar que una implementación cumple los requisitos aprobados.

**Impacto de modificarlos:** No deben modificarse sin proceso de revisión (son documentos aprobados).

---

### Decisiones arquitectónicas (ADRs)

| Archivo | Decisión clave |
|---------|---------------|
| `ADR-001-mvp-scope.md` | Mono-documento con análisis de calidad documental. |
| `ADR-002-knowledge-model.md` | Modelo híbrido: elementos tipados con relaciones opcionales. |
| `ADR-003-document-ingestion.md` | Formatos MD/TXT/PDF, capa de ingesta desacoplada. |
| `ADR-004-reliability-trust-model.md` | Trust by Evidence: source_ref + reproducibilidad acotada. |
| `ADR-005-privacy-external-processing.md` | Procesamiento externo con consentimiento + abstracción del proveedor. |
| `ADR-006-document-type-schemas.md` | 4 tipos de documento, selección híbrida, vocabulario de 4 relaciones. |

**Cuándo consultar:** Al diseñar cualquier feature nueva, para verificar que la implementación respeta las restricciones aprobadas.

**Impacto de modificarlos:** No se modifican; se crean nuevos ADRs si una decisión cambia.

---

### Documentación técnica

| Archivo | Propósito |
|---------|-----------|
| `docs/architecture/001-technology-stack.md` | Stack tecnológico completo, modelos LLM, estrategia de deploy, Pydantic models conceptuales del Knowledge Model. |
| `docs/deployment/local-setup.md` | Instrucciones de setup local. |
| `docs/deployment/supabase-setup.md` | Configuración de Supabase. |

---

### Steering files (contexto permanente para Kiro)

| Archivo | Propósito |
|---------|-----------|
| `.kiro/steering/coding.md` | Convenciones de código: inglés, docstrings, sin comentarios de historial. |
| `.kiro/steering/product.md` | Contexto de producto: alcance MVP, tipos de documento, principios. |
| `.kiro/steering/structure.md` | Estructura del repositorio y convenciones de organización. |
| `.kiro/steering/tech.md` | Stack técnico, principios arquitectónicos derivados de ADRs, restricciones permanentes. |

**Cuándo modificar:** Solo si cambian las convenciones del proyecto o se agregan nuevos principios derivados de ADRs.

---

### Spec de la feature implementada

| Archivo | Propósito |
|---------|-----------|
| `.kiro/specs/document-ingestion/requirements.md` | 7 Requirements con acceptance criteria para la ingesta. |
| `.kiro/specs/document-ingestion/design.md` | Diseño técnico completo: arquitectura, interfaces, API, data models, correctness properties. |
| `.kiro/specs/document-ingestion/tasks.md` | Plan de implementación: 12 tasks completadas, organizadas en 7 waves. |

**Relación entre spec y código:**

| Requirement | Módulos que lo implementan |
|-------------|---------------------------|
| R1 (Upload API) | `validator.py`, `documents.py`, `service.py` |
| R2 (Text Extraction) | `markdown_adapter.py`, `plaintext_adapter.py`, `pdf_adapter.py` |
| R3 (IR Generation) | `ir_builder.py`, `models/document.py` |
| R4 (Language Detection) | `language.py` |
| R5 (Temporary Storage) | `storage.py`, `001_create_documents.sql` |
| R6 (Upload Feedback) | `documents.py` (status endpoint) |
| R7 (Format-Independent) | `base.py` (FormatAdapter ABC), `models/document.py` (IR uniforme) |

---

## Flujo de datos

```
1. Cliente envía archivo (multipart/form-data)
         │
         ▼
2. documents.py recibe UploadFile
         │
         ▼
3. IngestionService.ingest()
    │
    ├── 3a. Validator.validate() ──── ¿Error? → return 400
    │
    ├── 3b. StorageService.create_document_record() (status=processing)
    │
    ├── 3c. StorageService.store_original() (Supabase Storage)
    │
    ├── 3d. adapter.extract() ──── ¿Error? → mark_failed, return 422
    │         └── Produce: ExtractionResult { chunks[], warnings[] }
    │
    ├── 3e. LanguageDetector.detect() → DetectedLanguage
    │
    ├── 3f. IRBuilder.build() → IntermediateRepresentation
    │
    └── 3g. StorageService.persist_ir() (status=ready)
         │
         ▼
4. Retorna DocumentStatus (202 Accepted)
```

---

## Dependencias externas

| Dependencia | Uso actual | Feature que la requiere |
|-------------|-----------|------------------------|
| `fastapi` | Framework web, routing, DI | Ingestion (actual) |
| `pydantic` | Modelos de dominio, validación, serialización | Ingestion (actual) |
| `pymupdf (fitz)` | Extracción de texto desde PDF | Ingestion (actual) |
| `supabase-py` | Cliente de DB y Storage | Ingestion (actual) |
| `python-multipart` | Parsing de multipart uploads | Ingestion (actual) |
| `uvicorn` | Servidor ASGI | Ingestion (actual) |
| `litellm` | Abstracción de proveedores LLM | Analysis Engine (próxima) |

---

## Principios arquitectónicos en el código actual

1. **Desacoplamiento por interfaces:** Los adapters implementan un ABC (`FormatAdapter`). Agregar un formato nuevo no requiere cambiar el pipeline.

2. **Inyección de dependencias:** `main.py` instancia los servicios y los inyecta. Los endpoints no crean dependencias; las reciben.

3. **Separación de responsabilidades:** Cada módulo tiene una única responsabilidad (validar, extraer, detectar idioma, ensamblar, persistir).

4. **Contrato estable:** `IntermediateRepresentation` es el contrato entre ingesta y análisis. El motor de análisis no necesitará conocer formatos de archivo.

5. **Privacidad por diseño:** `StorageService` no almacena metadata de usuario. Los documentos expiran automáticamente.

6. **Extensibilidad preparada:** La estructura permite agregar nuevos formatos (adapters), nuevos idiomas (language.py), y nuevas tablas (migrations) sin reestructurar lo existente.

---

## Qué falta para el MVP completo

El código actual cubre únicamente la **capacidad C1 (Ingreso de documentos)** del PRD. Las capacidades pendientes son:

- C2: Comprensión documental (Knowledge Model extraction)
- C3: Exploración del conocimiento (visualización)
- C4: Análisis de calidad documental
- C5: Asistencia mediante IA (consultas NL)
- C6: Modelo de confianza (source_ref verification)
- C7: Privacidad (consentimiento, transparencia — parcialmente cubierto por la abstracción)

El roadmap detallado se encuentra en `docs/architecture/mvp-roadmap.md`.
