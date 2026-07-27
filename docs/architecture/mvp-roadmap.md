# MVP Roadmap — Document Intelligence

> Fecha: 2026-07-25
> Basado en: PRD v0.6, ADRs 001-006, Spec MVP v0.6
> Estrategia: Desarrollo vertical (cada feature incluye backend + API + persistencia + UI mínima)

---

## Resumen del MVP

El MVP debe demostrar que un documento puede comprenderse mejor cuando se representa como conocimiento estructurado. Para ello, el sistema debe permitir:

1. Cargar un documento.
2. Generar un Knowledge Model (elementos tipados con relaciones opcionales).
3. Evaluar la calidad del documento (inconsistencias, faltantes, sugerencias).
4. Explorar y consultar el Knowledge Model.
5. Verificar el origen de cada resultado (Trust by Evidence).

---

## Features del MVP

### Feature 1: Document Ingestion

| Aspecto | Detalle |
|---------|---------|
| **Objetivo** | Permitir al usuario cargar un documento y transformarlo en una representación intermedia (IR) estructurada que el motor de análisis pueda consumir, independientemente del formato original. |
| **Estado** | ✅ Completada |
| **Capacidades PRD** | C1 (Ingreso de documentos) |
| **ADRs relacionados** | ADR-003 (formatos, tamaño, encoding, capa desacoplada), ADR-005 (retención limitada, sin user metadata) |
| **Dependencias** | Ninguna (feature fundacional) |
| **Entregable** | API REST funcional: upload → validate → extract → persist IR. Tres formatos soportados (MD, TXT, PDF). Detección de idioma. Almacenamiento temporal con expiración. |

**Componentes implementados:**
- Backend: pipeline completo (validator, 3 adapters, language detector, IR builder, storage)
- API: POST /upload, GET /{id}/status, GET /{id}/ir
- Persistencia: tablas documents + document_chunks, Supabase Storage
- Tests: unitarios e integración

---

### Feature 2: Application Shell & Document Upload UI

| Aspecto | Detalle |
|---------|---------|
| **Objetivo** | Crear la estructura base del frontend (React + TypeScript + Vite) con una interfaz mínima que permita cargar documentos y ver el estado del procesamiento. Establecer la infraestructura de comunicación con el backend. |
| **Estado** | ✅ Completada |
| **Capacidades PRD** | C1 (parte visual), C7 (consentimiento — UI del aviso previo al análisis) |
| **ADRs relacionados** | ADR-005 (transparencia: informar al usuario antes del procesamiento), ADR-003 (formatos soportados para la UI de upload) |
| **Dependencias** | Feature 1 (Document Ingestion — el backend de upload ya existe) |
| **Entregable** | Aplicación React funcional con: pantalla de upload (drag & drop o file picker), indicador de formatos soportados y límites, barra/indicador de progreso de procesamiento, pantalla de estado del documento, aviso de procesamiento externo con botón de consentimiento. |

**Alcance técnico:**
- Scaffolding: React 18 + TypeScript 5 + Vite + Tailwind + shadcn/ui
- Routing básico
- Cliente HTTP para comunicarse con el backend
- Estado global (Zustand) para documento activo
- Componente de consentimiento (ADR-005: informar y requerir autorización)

**Componentes implementados:**
- Frontend: Vite + React 18 + TypeScript 5 + Tailwind CSS + shadcn/ui + Zustand
- Componentes: AppShell, Header, UploadZone, FileInfo, ConsentDialog, UploadProgress, ProcessingStatus, ErrorDisplay, UploadPage
- Estado: Zustand uploadStore con state machine (idle→file-selected→consent→uploading→processing→ready/error)
- API client: documents.ts (upload con progreso + polling de status)
- i18n: Traducciones completas inglés + español
- Tests: Unit tests + integration test del flujo completo con MSW
- Backend: Configuración CORS

---

### Feature 3: Analysis Engine — Knowledge Model Extraction

| Aspecto | Detalle |
|---------|---------|
| **Objetivo** | Implementar el motor de análisis que consume el IR y produce un Knowledge Model: elementos tipados (propósito, conceptos, actores, reglas, procesos, restricciones) con relaciones opcionales (constrains, participates_in, depends_on, contradicts). Incluye inferencia de tipo de documento. |
| **Estado** | ✅ Completada |
| **Capacidades PRD** | C2 (Comprensión documental), C6 (Trust by Evidence — source_ref en cada elemento) |
| **ADRs relacionados** | ADR-002 (Knowledge Model híbrido, taxonomía fija, relaciones opcionales), ADR-004 (source_ref, verificación de evidencia, reproducibilidad), ADR-005 (solo enviar texto + prompts, abstracción del proveedor), ADR-006 (tipos de documento, inferencia + confirmación, vocabulario de relaciones) |
| **Dependencias** | Feature 1 (IR como input), Feature 2 (UI de consentimiento — debe existir antes de enviar al LLM) |
| **Entregable** | Pipeline de análisis: LLM abstraction layer (LiteLLM), prompts versionados para extracción, inferencia de tipo de documento, generación del Knowledge Model con source_ref por elemento, verificación de evidencia. API endpoints para iniciar análisis y obtener resultados. UI mínima para confirmar tipo de documento y ver estado del análisis. |

**Alcance técnico:**
- Backend: LLM abstraction layer, prompt templates, Knowledge Model Pydantic models, analysis service
- API: POST /analyze, GET /{id}/knowledge-model, POST /{id}/confirm-type
- Persistencia: tabla knowledge_elements, tabla analysis_sessions
- Frontend: selector de tipo de documento (inferencia + confirmación), indicador de progreso del análisis

**Componentes implementados:**
- Backend: AnalysisService (orquestador), LLM client (LiteLLM), extraction service, type inference, evidence verification
- Prompts: Templates versionados para extracción e inferencia de tipo
- Modelos: KnowledgeElement, KnowledgeModel, AnalysisSession, SourceRef, Relation, ExtractionMetadata
- API: POST /analyze, POST /confirm-type, GET /knowledge-model
- Persistencia: Tablas analysis_sessions + knowledge_elements
- Tests: Unitarios e integración

---

### Feature 4: Knowledge Model Visualization & Exploration

| Aspecto | Detalle |
|---------|---------|
| **Objetivo** | Permitir al usuario visualizar y explorar los elementos del Knowledge Model de forma estructurada. Navegar relaciones entre elementos. Ver la evidencia (source_ref) de cada elemento. |
| **Estado** | ✅ Completada |
| **Capacidades PRD** | C3 (Exploración del conocimiento), C6 (visualización de source_ref) |
| **ADRs relacionados** | ADR-002 (elementos tipados con relaciones → visualización), ADR-004 (source_ref visible al usuario para verificación) |
| **Dependencias** | Feature 3 (Knowledge Model generado) |
| **Entregable** | Vista principal del Knowledge Model: lista/grid de elementos agrupados por tipo, panel de detalle con contenido y evidencia, visualización de relaciones (React Flow o lista), indicación de elementos no-verificados, navegación entre elementos relacionados. |

**Alcance técnico:**
- Frontend: componentes de visualización de elementos, panel de detalle, vista de relaciones (graph o lista según complejidad)
- Backend: endpoint GET /{id}/knowledge-model ya existe desde Feature 3
- Sin lógica de backend adicional significativa

**Componentes implementados:**
- Frontend: 15 componentes React para visualización del KM
- Vistas: Lista agrupada por tipo + grafo de relaciones (React Flow + dagre)
- Panel de detalle: Contenido completo, evidencia, elementos relacionados, navegación con historial
- Accesibilidad: jest-axe, navegación por teclado, focus management, lista accesible alternativa, encoding no-cromático
- Estado: knowledgeModelStore (Zustand) con cache, navigation history (cap 50), view mode
- Tests: 382 tests en 31 archivos (unit, component, property-based con fast-check, accessibility)

---

### Feature 5: Document Quality Analysis

| Aspecto | Detalle |
|---------|---------|
| **Objetivo** | Evaluar la calidad del documento basándose en el Knowledge Model: detectar inconsistencias internas (contradicciones, ambigüedades), identificar información faltante según el esquema del tipo de documento, y generar sugerencias de mejora. |
| **Estado** | ✅ Completada |
| **Capacidades PRD** | C4 (Análisis de calidad documental) |
| **ADRs relacionados** | ADR-001 (inconsistencias internas como diferenciador del MVP), ADR-002 (relaciones tipo contradicts para detección), ADR-004 (source_ref en hallazgos), ADR-006 (esquemas por tipo para evaluar completitud, Generic sin evaluación de completitud) |
| **Dependencias** | Feature 3 (Knowledge Model + tipo de documento confirmado) |
| **Entregable** | Pipeline de análisis de calidad: detección de contradicciones, detección de ambigüedades, evaluación de completitud (por tipo), generación de sugerencias. API para obtener resultados de calidad. UI que muestre inconsistencias, faltantes y sugerencias con evidencia trazable. |

**Alcance técnico:**
- Backend: quality analysis service, prompts específicos para cada tipo de análisis, modelos Pydantic (Inconsistency, MissingElement, Suggestion)
- API: POST /{id}/quality-analysis, GET /{id}/quality-analysis
- Persistencia: resultados almacenados en columnas JSONB de analysis_sessions (migración 003)
- Detectors: ContradictionDetector, AmbiguityDetector, CompletenessEvaluator, SuggestionGenerator, FindingVerifier

**Componentes implementados:**
- Backend: QualityAnalysisService (orquestador), 4 detectores/evaluadores, finding verifier, prompt templates versionados
- Modelos: QualityAnalysisResult, Inconsistency, MissingElement, Suggestion, FindingSourceRef, QualityAnalysisMetadata
- Document type schemas: PRD, technical_spec, policy_process (con elementos esperados por tipo)
- API: POST/GET /{id}/quality-analysis con estados (analyzing, completed, failed)
- Persistencia: Migración 003 (columnas quality_* en analysis_sessions)
- Tests: Unitarios para cada detector, modelos, schemas, prompts e integración del flujo completo

---

### Feature 6: Natural Language Queries

| Aspecto | Detalle |
|---------|---------|
| **Objetivo** | Permitir al usuario realizar preguntas en lenguaje natural sobre el documento. Las respuestas se basan en el Knowledge Model y incluyen evidencia trazable (source_ref) al documento original. |
| **Estado** | 🔲 Pendiente |
| **Capacidades PRD** | C5 (Asistencia mediante IA) |
| **ADRs relacionados** | ADR-004 (evidencia trazable en respuestas), ADR-005 (solo enviar lo necesario al LLM) |
| **Dependencias** | Feature 3 (Knowledge Model como contexto para respuestas) |
| **Entregable** | Interfaz de chat/consulta integrada en la aplicación. El backend recibe la pregunta, construye contexto desde el Knowledge Model, consulta al LLM, y retorna una respuesta con referencias al documento. |

**Alcance técnico:**
- Backend: query service, prompt construction con Knowledge Model como contexto, response parsing con source_ref
- API: POST /{id}/query
- Frontend: panel de chat/consulta, respuestas con evidencia clicable/navegable

---

### Feature 7: User Feedback (Should Have)

| Aspecto | Detalle |
|---------|---------|
| **Objetivo** | Permitir al usuario marcar elementos del Knowledge Model como incorrectos o irrelevantes. Feedback pasivo almacenado para mejora futura. |
| **Estado** | 🔲 Pendiente (Should Have — implementar si el tiempo lo permite) |
| **Capacidades PRD** | C6 (parte Should Have del modelo de confianza) |
| **ADRs relacionados** | ADR-004 (feedback pasivo como Should Have: marcar incorrecto/irrelevante, sin edición ni re-procesamiento) |
| **Dependencias** | Feature 4 (visualización del Knowledge Model donde el usuario interactúa con elementos) |
| **Entregable** | Botones de feedback en cada elemento visible. Backend almacena feedback asociado al análisis. Sin lógica de re-procesamiento. |

**Alcance técnico:**
- Backend: endpoint POST /{id}/elements/{element_id}/feedback, tabla de feedback
- Frontend: botones "incorrecto" / "irrelevante" en panel de detalle de elemento
- Mínimo esfuerzo; valor diferido a iteraciones futuras

---

### Feature 11: Analysis Quality v2

| Aspecto | Detalle |
|---------|---------|
| **Objetivo** | Rediseñar los análisis on-demand para que comprendan el PROPÓSITO FUNCIONAL del documento (no solo su estructura visual), mejorar transparencia de modelo, corregir fallback, y mejorar detección de idioma. |
| **Estado** | 🚧 En desarrollo |
| **Capacidades PRD** | C3 (mejora de calidad), C5 (transparencia de modelo) |
| **ADRs relacionados** | ADR-007 (rediseño estructural), ADR-009 (rediseño de calidad) |
| **Dependencias** | Feature 8 (Base Analysis — clasificación), Feature 9 (On-Demand Analysis — prompts existentes) |
| **Entregable** | Prompts v2 para los 4 análisis (funcional, no visual), model_id real propagado al frontend, errores clasificados (cuota/timeout/auth), fallback cross-provider, detección de idioma mejorada (pt, fr), nuevos modelos en selector. |

**Alcance técnico:**
- Backend: AnalyzerResponse dataclass, prompts v2 (build_index, questions, conclusions, relations), LLMQuotaExhaustedError, cross-provider fallback, language detector ampliado
- Modelos: StructureNode +functional_group/original_headings, QuestionsResult +coherence_note, Observation categories actualizadas, SectionRelation types actualizados
- Frontend: badge de modelo en resultados, errores diferenciados, nuevos modelos en selector
- Spec: `.kiro/specs/analysis-quality-v2/`

---

### Feature 12: Analysis Workspace UI (pendiente)

| Aspecto | Detalle |
|---------|---------|
| **Objetivo** | Rediseñar el layout post-análisis con dos paneles (opciones a la izquierda, resultados a la derecha), navegación entre documentos analizados, persistencia de análisis independiente del documento temporal. |
| **Estado** | 🔲 Pendiente |
| **Capacidades PRD** | C3 (exploración), C6 (persistencia) |
| **ADRs relacionados** | ADR-007 (análisis progresivo) |
| **Dependencias** | Feature 11 (Analysis Quality v2 — resultados mejorados para visualizar) |
| **Entregable** | Layout de dos columnas para desktop, navegación entre documentos previos, tabla analyzed_documents para persistencia, upload sin perder análisis previos. |

**Alcance técnico:**
- Backend: tabla analyzed_documents, endpoints para listar documentos previos y sus análisis
- Frontend: AnalysisWorkspace (layout 2 columnas), documentListStore, tabs para resultados, responsive (vertical en mobile)
- Spec: `.kiro/specs/analysis-workspace-ui/` (por crear)

---

### Feature 13: Document Card Redesign (C2 evolution)

| Aspecto | Detalle |
|---------|---------|
| **Objetivo** | Rediseñar la Document Card para separar la ficha técnica (local, instantánea) del contenido (LLM). Incorporar clasificación formal de 4 niveles basada en tipologías documentales ISO/archivística. Reducir dependencia del LLM usando lingua-py y textstat. |
| **Estado** | 🔲 Pendiente |
| **Capacidades PRD** | C2 (evolución de análisis base) |
| **ADRs relacionados** | ADR-007 (análisis progresivo), ADR-009 (calidad de análisis — clasificación como input) |
| **Dependencias** | Feature 8 (Base Analysis — evoluciona la card existente) |
| **Entregable** | Card con dos secciones (Ficha Técnica + Contenido), taxonomía 4 niveles con confidence, lingua-py para idioma, textstat para legibilidad, prompt v3 reducido, hints de clasificación local. |

**Alcance técnico:**
- Backend: TextStatsAnalyzer (textstat), lingua-py language detection, classification.py (4 enums + DocumentClassificationResult), prompts_v3.py, LocalAnalyzer v2 (hints), LLMAnalyzer v3
- Frontend: DocumentCardView rewrite (dos secciones, collapsibles, tooltips), ProcessingStatus simplificado
- Modelos: TextStats, ClassificationHints, LLMAnalysisResultV3, DocumentCard extendido
- Dependencias nuevas: lingua-language-detector>=2.0.0, textstat>=0.7.0
- Spec: `.kiro/specs/document-card-redesign/`

---

## Diagrama de dependencias

```
Feature 1: Document Ingestion ✅
    │
    ▼
Feature 2: Application Shell & Upload UI ✅
    │
    ▼
Feature 3: Analysis Engine (Knowledge Model Extraction) ✅
    │
    ├─────────────────────┬──────────────────────┐
    ▼                     ▼                      ▼
Feature 4:          Feature 5:             Feature 6:
Visualization ✅    Quality Analysis ✅    NL Queries ✅
    │
    ▼
Feature 7: User Feedback (Should Have)

Feature 8: Base Analysis (C2) ✅
    │
    ├──────────────────────────────────────────────┐
    ▼                                              ▼
Feature 9: On-Demand Analysis (C3) ✅    Feature 13: Document Card Redesign 🔲
    │                                              │
    ├──── Feature 10: User Preferences (C5) ✅    │
    ▼                                              ▼
Feature 11: Analysis Quality v2 🚧 ◀──────────────┘
    │
    ▼
Feature 12: Analysis Workspace UI 🔲
```

---

## Resumen de estado

| # | Feature | Estado | Prioridad | Esfuerzo estimado |
|---|---------|--------|-----------|-------------------|
| 1 | Document Ingestion | ✅ Completada | Must Have | — |
| 2 | Application Shell & Upload UI | ✅ Completada | Must Have | — |
| 3 | Analysis Engine (KM Extraction) | ✅ Completada | Must Have | — |
| 4 | KM Visualization & Exploration | ✅ Completada | Must Have | — |
| 5 | Document Quality Analysis | ✅ Completada | Must Have | — |
| 6 | Natural Language Queries | ✅ Completada | Must Have | — |
| 7 | User Feedback | 🔲 Pendiente | Should Have | Bajo |
| 8 | Base Analysis (C2) | ✅ Completada | Must Have | — |
| 9 | On-Demand Analysis (C3) | ✅ Completada | Must Have | — |
| 10 | User Preferences (C5) | ✅ Completada | Must Have | — |
| 11 | Analysis Quality v2 | 🚧 En desarrollo | Must Have | Alto |
| 12 | Analysis Workspace UI | 🔲 Pendiente | Must Have | Medio |
| 13 | Document Card Redesign | 🔲 Pendiente | Must Have | Medio |

---

## Cobertura del PRD por feature

| Capacidad PRD | Feature(s) que la implementan |
|---------------|-------------------------------|
| C1 — Ingreso de documentos | Feature 1 (backend) + Feature 2 (UI) |
| C2 — Comprensión documental | Feature 3, Feature 8 (base analysis), Feature 13 (card redesign) |
| C3 — Exploración del conocimiento | Feature 4 |
| C4 — Análisis de calidad documental | Feature 5 |
| C5 — Asistencia mediante IA | Feature 6 |
| C6 — Modelo de confianza | Feature 3 (source_ref) + Feature 4 (visualización) + Feature 7 (feedback) |
| C7 — Privacidad y procesamiento | Feature 2 (consentimiento UI) + Feature 3 (abstracción proveedor) |

---

## Cobertura de ADRs por feature

| ADR | Features afectadas |
|-----|-------------------|
| ADR-001 (MVP scope) | Todas — define qué incluye el MVP |
| ADR-002 (Knowledge Model) | Feature 3, 4, 5 |
| ADR-003 (Document Ingestion) | Feature 1, 2 |
| ADR-004 (Reliability/Trust) | Feature 3, 4, 5, 6, 7, 8, 9, 11 |
| ADR-005 (Privacy) | Feature 2, 3 |
| ADR-006 (Document Types) | Feature 3, 5, 8, 11 |
| ADR-007 (Structural Analysis Redesign) | Feature 8, 9, 11, 13 |
| ADR-008 (LLM Context Caching) | Feature 9 (optimización futura) |
| ADR-009 (Analysis Quality Redesign) | Feature 11, 13 |

---

## Notas sobre la estrategia de implementación

A partir de Feature 2, se adopta un enfoque de **desarrollo vertical**: cada feature incluye backend, API, persistencia e interfaz mínima. El objetivo es disponer de una aplicación funcional en cada incremento, aunque las capacidades sean básicas.

La secuencia propuesta prioriza:
1. Tener una UI funcional lo antes posible (Feature 2).
2. Implementar el corazón del producto (Feature 3 — el motor de análisis).
3. Hacer visible el resultado (Feature 4 — visualización).
4. Agregar el diferenciador principal (Feature 5 — calidad documental).
5. Completar la interactividad (Feature 6 — consultas NL).
6. Agregar valor incremental si hay tiempo (Feature 7 — feedback).

La revisión detallada del orden de implementación bajo el enfoque vertical se encuentra en la sección final de este documento.

---

## Recomendación de orden de implementación (enfoque vertical)

### Orden propuesto

1. **Feature 2** — Application Shell & Upload UI
2. **Feature 3** — Analysis Engine (Knowledge Model Extraction)
3. **Feature 4** — KM Visualization & Exploration
4. **Feature 5** — Document Quality Analysis
5. **Feature 6** — Natural Language Queries
6. **Feature 7** — User Feedback (si hay tiempo)

### Justificación

- **Feature 2 primero** porque establece la infraestructura del frontend que todas las features posteriores necesitarán. Sin ella, no hay forma de demostrar ni validar visualmente nada.

- **Feature 3 después** porque es el núcleo del producto. Sin Knowledge Model no hay nada que visualizar, analizar ni consultar. Además, el consentimiento del usuario (implementado en Feature 2) es prerequisito para enviar datos al LLM.

- **Feature 4 antes de Feature 5** porque la visualización del Knowledge Model es necesaria para que el usuario entienda los resultados del análisis de calidad. Sin ver los elementos, las inconsistencias y faltantes no tienen contexto.

- **Feature 5 antes de Feature 6** porque la detección de inconsistencias es el diferenciador principal del producto (ADR-001). Las consultas NL son valiosas pero no son el diferenciador.

- **Feature 6 al final de los Must Have** porque puede construirse incrementalmente sobre la infraestructura LLM ya creada en Feature 3. Es la feature más "independiente" una vez que el Knowledge Model existe.

- **Feature 7 última** porque es Should Have y su valor es diferido (datos para mejora futura, no funcionalidad inmediata para el usuario).

### Oportunidades de paralelización

- Features 4, 5 y 6 son independientes entre sí (todas dependen de Feature 3 pero no entre ellas). Si hay capacidad, pueden desarrollarse en paralelo.
- Feature 7 es tan ligera que podría integrarse como parte de Feature 4 (agregar los botones de feedback durante la visualización).

### Cambios respecto al enfoque anterior

El enfoque anterior (backend-first) habría implementado todo el motor de análisis, calidad y consultas antes de crear cualquier interfaz. El enfoque vertical propuesto:

- Adelanta Feature 2 (frontend shell) para tener feedback visual desde el inicio.
- Cada feature es demostrable individualmente.
- Reduce el riesgo de llegar al final con un backend completo pero sin forma de validarlo con usuarios.
