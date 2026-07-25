# 002 — Arquitectura actual del sistema

> Fecha: 2026-07-25  
> Estado de la implementación: Features 1–4 completadas  
> Próxima feature pendiente: Document Quality Analysis (Feature 5)

---

## Propósito de este documento

Este documento describe la arquitectura implementada hasta la fecha, clasificando cada archivo y módulo del proyecto por su responsabilidad, interacciones y relación con los requisitos aprobados. Su objetivo es que un desarrollador nuevo pueda comprender rápidamente la estructura, localizar dónde realizar cambios y anticipar el impacto de una modificación.

---

## Vista general del sistema

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        Document Intelligence                              │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────┐     │
│  │                     Frontend (React + Vite)                      │     │
│  │                                                                  │     │
│  │  ┌─────────────┐  ┌──────────────────┐  ┌─────────────────┐    │     │
│  │  │  App Shell   │  │  Upload UI       │  │  Knowledge Model │    │     │
│  │  │  (Header,    │  │  (Dropzone,      │  │  Visualization   │    │     │
│  │  │   Layout)    │  │   Consent,       │  │  (List, Detail,  │    │     │
│  │  │             │  │   Progress)      │  │   Graph, A11y)  │    │     │
│  │  └─────────────┘  └──────────────────┘  └─────────────────┘    │     │
│  │                                                                  │     │
│  │  ┌─────────────────┐  ┌──────────────┐  ┌──────────────────┐   │     │
│  │  │  Zustand Stores  │  │  API Client  │  │  i18n (en/es)    │   │     │
│  │  │  (upload, km)    │  │  (HTTP)      │  │                  │   │     │
│  │  └─────────────────┘  └──────┬───────┘  └──────────────────┘   │     │
│  └───────────────────────────────┼─────────────────────────────────┘     │
│                                  │ HTTPS (CORS)                           │
│                                  ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐     │
│  │                    Backend (FastAPI)                              │     │
│  │                                                                  │     │
│  │  ┌──────────┐   ┌────────────────────┐  ┌─────────────────┐    │     │
│  │  │ API v1   │──▶│  Ingestion Service  │  │ Analysis Service │    │     │
│  │  │          │──▶│  (pipeline)         │  │ (LLM pipeline)  │    │     │
│  │  └──────────┘   └────────────────────┘  └─────────────────┘    │     │
│  │                      │ │ │ │ │                │ │ │             │     │
│  │       ┌──────────────┘ │ │ │ └────────┐      │ │ └──────┐     │     │
│  │       ▼                ▼ │ ▼            ▼     ▼ ▼        ▼     │     │
│  │  ┌──────────┐ ┌──────┐│┌────────┐┌──────┐┌──────┐┌────────┐  │     │
│  │  │Validator │ │Adapt.│││Lang Det.││IR Bld││LiteLLM││Verificn│  │     │
│  │  └──────────┘ └──────┘│└────────┘└──────┘└──────┘└────────┘  │     │
│  │                        ▼                                       │     │
│  │                ┌──────────────┐                                │     │
│  │                │   Storage    │                                │     │
│  │                │   Service    │                                │     │
│  │                └──────┬───────┘                                │     │
│  └───────────────────────┼────────────────────────────────────────┘     │
│                           ▼                                              │
│                 ┌──────────────────┐                                     │
│                 │    Supabase      │                                     │
│                 │ (PostgreSQL +    │                                     │
│                 │  Storage)        │                                     │
│                 └──────────────────┘                                     │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Módulos del frontend

### 1. Infraestructura y configuración

| Archivo | Responsabilidad |
|---------|----------------|
| `src/frontend/src/main.tsx` | Entry point: monta React en el DOM, envuelve en TranslationProvider. |
| `src/frontend/src/App.tsx` | Componente raíz: renderiza AppShell con UploadPage. |
| `src/frontend/vite.config.ts` | Configuración de Vite con path aliases (`@/`). |
| `src/frontend/package.json` | Dependencias y scripts (dev, build, test). |

### 2. Capa de API (HTTP)

| Archivo | Responsabilidad |
|---------|----------------|
| `src/frontend/src/api/client.ts` | Constantes de configuración: `API_BASE_URL`, timeouts, polling intervals. |
| `src/frontend/src/api/documents.ts` | `uploadDocument()` (XHR con progreso), `getDocumentStatus()` (fetch con abort). |
| `src/frontend/src/api/knowledgeModel.ts` | `getKnowledgeModel(documentId)` con 30s timeout y error handling tipado. |

### 3. Tipos TypeScript

| Archivo | Responsabilidad |
|---------|----------------|
| `src/frontend/src/types/api.ts` | Interfaces de upload: `UploadResponse`, `StatusResponse`, `ApiErrorResponse`. |
| `src/frontend/src/types/knowledgeModel.ts` | Interfaces del KM: `KnowledgeModelResponse`, `KnowledgeElementResponse`, `SourceRefResponse`, `RelationResponse`, `ExtractionMetadataResponse`. |

### 4. Estado global (Zustand)

| Archivo | Responsabilidad |
|---------|----------------|
| `src/frontend/src/store/uploadStore.ts` | Estado del flujo de upload: state machine (idle→file-selected→consent→uploading→processing→ready/error), polling, reset. |
| `src/frontend/src/store/knowledgeModelStore.ts` | Estado del Knowledge Model: status (idle/loading/loaded/error/empty), cache, selection, navigation history (cap 50), view mode (list/graph). |

### 5. Internacionalización

| Archivo | Responsabilidad |
|---------|----------------|
| `src/frontend/src/i18n/index.ts` | `TranslationProvider` (context), hook `useTranslation()` con interpolación. |
| `src/frontend/src/i18n/en.json` | Traducciones inglés (upload, consent, status, errors, km). |
| `src/frontend/src/i18n/es.json` | Traducciones español. |

### 6. Componentes — Layout

| Archivo | Responsabilidad |
|---------|----------------|
| `components/layout/AppShell.tsx` | Layout: Header + render condicional (UploadPage o KnowledgeModelPage). |
| `components/layout/Header.tsx` | Header con nombre de la app, responsive. |

### 7. Componentes — Upload (Feature 2)

| Archivo | Responsabilidad |
|---------|----------------|
| `components/upload/UploadZone.tsx` | Drag & drop + file picker con validación client-side. |
| `components/upload/FileInfo.tsx` | Nombre, formato y tamaño del archivo seleccionado. |
| `components/upload/ConsentDialog.tsx` | Diálogo de aviso de procesamiento externo (ADR-005). |
| `components/upload/UploadProgress.tsx` | Barra de progreso + indicador de cold-start. |
| `components/upload/ProcessingStatus.tsx` | Spinner durante polling + resultado al completar. |
| `components/upload/ErrorDisplay.tsx` | Mensaje de error con retry/start over. |
| `components/upload/UploadPage.tsx` | Orquestador: renderiza según step del store. |

### 8. Componentes — Knowledge Model (Feature 4)

| Archivo | Responsabilidad |
|---------|----------------|
| `components/knowledge-model/KnowledgeModelPage.tsx` | Orquestador: fetch on mount, render por status, layout master-detail responsive. |
| `components/knowledge-model/KMHeader.tsx` | Título, tasa de verificación, toggle list/graph. |
| `components/knowledge-model/ElementListView.tsx` | Agrupa elementos por tipo (taxonomía fija de 6 tipos). |
| `components/knowledge-model/TypeGroup.tsx` | Sección colapsable por tipo, heading h3, count badge, listbox. |
| `components/knowledge-model/ElementCard.tsx` | Tarjeta: nombre, descripción truncada, ícono verificación, selección click/teclado. |
| `components/knowledge-model/ElementDetailPanel.tsx` | Panel detalle responsive: nombre, tipo, contenido, evidence, relaciones, back+Escape. |
| `components/knowledge-model/EvidenceSection.tsx` | Blockquote evidencia, metadata contextual, verificación, error boundary. |
| `components/knowledge-model/RelatedElements.tsx` | Lista de elementos relacionados con navegación (push history). |
| `components/knowledge-model/LoadingState.tsx` | Spinner + mensaje i18n. |
| `components/knowledge-model/EmptyState.tsx` | Mensaje cuando no hay elementos extraídos. |
| `components/knowledge-model/ErrorState.tsx` | Error + botón retry. |
| `components/knowledge-model/RelationshipGraphView.tsx` | Canvas React Flow con dagre layout + toggle a vista accesible. |
| `components/knowledge-model/ElementNode.tsx` | Nodo custom React Flow: color + ícono único por tipo. |
| `components/knowledge-model/RelationshipEdge.tsx` | Edge custom: label visible, contradicts con línea punteada roja. |
| `components/knowledge-model/AccessibleRelationshipList.tsx` | Lista textual accesible alternativa al grafo. |

### 9. Utilidades

| Archivo | Responsabilidad |
|---------|----------------|
| `src/frontend/src/lib/utils.ts` | `cn()` (clsx + tailwind-merge), `formatBytes()`. |
| `src/frontend/src/lib/validation.ts` | `validateFile()` — formato y tamaño client-side. |
| `src/frontend/src/lib/graphLayout.ts` | `applyDagreLayout(nodes, edges)` — dagre TB layout. |

---

## Módulos del backend

### 1. Capa de entrada — API HTTP

| Archivo | Responsabilidad |
|---------|----------------|
| `src/backend/app/main.py` | Application factory: FastAPI, CORS, DI, routers. |
| `src/backend/app/api/v1/documents.py` | Endpoints ingesta: `POST /upload`, `GET /{id}/status`, `GET /{id}/ir`. |
| `src/backend/app/api/v1/analysis.py` | Endpoints análisis: `POST /{id}/analyze`, `POST /{id}/confirm-type`, `GET /{id}/knowledge-model`. |

### 2. Motor de análisis (Feature 3)

| Archivo | Responsabilidad |
|---------|----------------|
| `app/analysis/service.py` | `AnalysisService` — Orquesta: type inference → confirmation → extraction → verification. |
| `app/analysis/llm_client.py` | Abstracción LLM sobre LiteLLM. |
| `app/analysis/extraction.py` | Extracción del Knowledge Model desde el IR con prompts versionados. |
| `app/analysis/type_inference.py` | Inferencia de tipo de documento con LLM. |
| `app/analysis/verification.py` | Verificación de evidencia: valida source_ref contra chunks del IR. |
| `app/analysis/prompts/` | Templates versionados (extraction_v1.py, type_inference_v1.py). |

### 3. Modelos de dominio

| Archivo | Responsabilidad |
|---------|----------------|
| `app/models/document.py` | Modelos de ingesta: `DocumentFormat`, `IntermediateRepresentation`, `DocumentStatus`, etc. |
| `app/models/knowledge_model.py` | Modelos del KM: `KnowledgeElement`, `KnowledgeModel`, `SourceRef`, `Relation`, `AnalysisSession`, `TypeSuggestion`. |

### 4. Pipeline de ingesta (Feature 1)

| Módulo | Archivo | Responsabilidad |
|--------|---------|----------------|
| Orquestador | `app/ingestion/service.py` | Pipeline: validate → store → extract → detect language → build IR → persist. |
| Validación | `app/ingestion/validator.py` | Formato, tamaño, encoding. |
| Adaptadores | `app/ingestion/adapters/*.py` | Markdown, PlainText, PDF. |
| Idioma | `app/ingestion/language.py` | Detección es/en/unknown. |
| IR | `app/ingestion/ir_builder.py` | Ensamblaje y validación del IR. |
| Persistencia | `app/ingestion/storage.py` | CRUD contra Supabase. |

### 5. Base de datos

| Archivo | Responsabilidad |
|---------|----------------|
| `app/db/migrations/001_create_documents.sql` | Tablas `documents` + `document_chunks`. |
| `app/db/migrations/002_create_analysis.sql` | Tablas `analysis_sessions` + `knowledge_elements`. |

---

## Flujo de datos completo

```
1. Usuario carga documento (drag & drop o file picker)
         │
         ▼
2. ConsentDialog → acceptConsent() → uploadDocument(file)
         │
         ▼
3. Backend: POST /upload → IngestionService.ingest()
    ├── validate → store → extract → detect language → build IR → persist
    └── Retorna 202 (document_id, status=processing)
         │
         ▼
4. Frontend: polling GET /{id}/status cada 2s
         │
         ▼
5. status=ready → AppShell muestra KnowledgeModelPage
         │
         ▼
6. Frontend: GET /{id}/knowledge-model (30s timeout)
         │
         ▼
7. Backend: AnalysisService.get_knowledge_model() → 200
         │
         ▼
8. Store carga KM → renderiza list/graph + detail panel
```

---

## Dependencias externas

| Dependencia | Uso | Capa |
|-------------|-----|------|
| `fastapi` | Framework web, routing, DI | Backend |
| `pydantic` | Modelos de dominio, validación | Backend |
| `pymupdf` | Extracción de texto desde PDF | Backend |
| `supabase-py` | Cliente DB + Storage | Backend |
| `litellm` | Abstracción proveedores LLM | Backend |
| `uvicorn` | Servidor ASGI | Backend |
| `react` / `react-dom` | UI framework | Frontend |
| `zustand` | Estado global | Frontend |
| `reactflow` | Visualización de grafos | Frontend |
| `@dagrejs/dagre` | Layout automático de grafos | Frontend |
| `tailwindcss` | CSS utility-first | Frontend |
| `vite` | Build tool y dev server | Frontend |
| `vitest` | Testing framework | Frontend |
| `fast-check` | Property-based testing | Frontend |
| `jest-axe` | Accessibility testing (axe-core) | Frontend |

---

## Principios arquitectónicos

1. **Desacoplamiento por interfaces:** Adapters del backend implementan un ABC. Componentes del frontend se comunican solo a través del store.

2. **Inyección de dependencias:** Backend usa DI de FastAPI. Frontend usa hooks Zustand.

3. **Separación de responsabilidades:** Cada módulo tiene una responsabilidad única. Frontend: pages → features → primitivos.

4. **Contratos estables:** `IntermediateRepresentation` entre ingesta y análisis. Tipos TypeScript (`KnowledgeModelResponse`) entre API y frontend.

5. **Privacidad por diseño:** Consentimiento explícito, retención temporal, sin metadata de usuario.

6. **Accesibilidad integrada:** ARIA, keyboard navigation, focus management, non-color encoding, jest-axe.

7. **Internacionalización completa:** Todos los strings vía i18n (en/es). Sin hardcoding.

8. **Correctness Properties:** PBT con fast-check (data integrity, cache validity, navigation history).

---

## Qué falta para el MVP completo

Capacidades pendientes:

- **C4:** Análisis de calidad documental (Feature 5)
- **C5:** Asistencia mediante IA — consultas NL (Feature 6)
- **C6 parcial:** Feedback pasivo (Feature 7)

Roadmap detallado: `docs/architecture/mvp-roadmap.md`
