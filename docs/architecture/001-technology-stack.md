# 001 — Stack Tecnológico del MVP

> Estado: **Aprobada**
> Fecha: 2026-07-23
> Depende de: ADR-001 a ADR-006 (todas aprobadas)

---

## Contexto

Los ADR-001 a ADR-006 definieron qué hace el MVP, cómo representa el conocimiento, qué formatos acepta, cómo gestiona la confianza, la privacidad y los tipos de documento. Falta definir con qué tecnologías se construye.

Este documento registra las decisiones de stack tecnológico tomadas durante la fase de diseño técnico. A diferencia de los ADR (que documentan decisiones arquitectónicas de producto), este documento registra decisiones de implementación que pueden evolucionar sin impactar la arquitectura del producto.

---

## Decisiones tomadas

### D-01 — Lenguaje del backend: Python 3.12+

**Razón:** Ecosistema de IA maduro (SDKs oficiales de todos los proveedores, LiteLLM, librerías de parsing). Desarrollo rápido para hackathon. FastAPI con Pydantic permite definir los schemas del Knowledge Model con validación nativa.

**Alternativas descartadas:**
- Node.js/TypeScript: ecosistema de IA menos maduro, parsing de PDF más limitado.
- Go: desarrollo más lento para prototipado, menos librerías de IA.

---

### D-02 — Framework web: FastAPI

**Razón:** Async nativo, tipado con Pydantic (genera OpenAPI automáticamente), rendimiento alto, comunidad activa. Los modelos Pydantic del Knowledge Model sirven tanto para validación interna como para documentación de API.

---

### D-03 — Frontend: React + TypeScript + Vite

**Razón:** Ecosistema maduro, componentización, tipado fuerte. Vite ofrece HMR instantáneo para desarrollo. Tailwind + shadcn/ui permiten construir UI rápidamente sin diseñar componentes desde cero. shadcn/ui provee componentes accesibles que se copian al proyecto (sin dependencia runtime pesada).

---

### D-04 — Base de datos: Supabase (PostgreSQL cloud)

**Razón:** Experiencia previa del equipo con Supabase. Free tier generoso (500 MB DB, 1 GB storage). PostgreSQL soporta `jsonb` nativo para almacenar el Knowledge Model con capacidad de consulta. Elimina la necesidad de infraestructura de base de datos propia. Auth y Storage incluidos para iteraciones futuras.

**Alternativas descartadas:**
- SQLite: sin experiencia del equipo, no escala en serverless/containers, requiere migración futura.
- PostgreSQL self-hosted: infraestructura innecesaria para MVP.

**Uso previsto en el MVP:**

```sql
-- Tabla principal: sesiones de análisis
CREATE TABLE analysis_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT now(),
    document_name TEXT NOT NULL,
    document_type TEXT NOT NULL,  -- 'prd', 'technical_spec', 'policy_process', 'generic'
    document_type_confirmed BOOLEAN DEFAULT false,
    status TEXT DEFAULT 'pending',  -- 'pending', 'processing', 'completed', 'error'
    knowledge_model JSONB,  -- Knowledge Model completo
    quality_analysis JSONB,  -- Inconsistencias, faltantes, sugerencias
    metadata JSONB  -- Info adicional: idioma detectado, tamaño, formato original
);

-- El documento original NO se persiste en DB (ADR-005: retención limitada)
-- Se almacena temporalmente en memoria/storage durante el procesamiento
```

---

### D-05 — Abstracción del LLM: LiteLLM

**Razón:** Cumple directamente ADR-005 (proveedor reemplazable sin modificar pipeline). Soporta 100+ proveedores con la misma interfaz. Permite routing multi-modelo, fallbacks automáticos, y rate limiting. Una línea de config cambia el proveedor.

**Configuración conceptual:**

```python
# config/llm_config.py
from litellm import completion

# Modelo principal para extracción del Knowledge Model
EXTRACTION_MODEL = "gemini/gemini-2.5-flash-preview-05-20"

# Modelo para tareas ligeras (clasificación de tipo, verificación)
LIGHT_MODEL = "groq/llama-3.3-70b-versatile"

# Modelo para verificación de evidencia
VERIFICATION_MODEL = "groq/llama-3.1-8b-instant"

# Fallback si el modelo principal tiene rate limit
FALLBACK_MODEL = "groq/llama-3.3-70b-versatile"


async def call_llm(prompt: str, model: str = EXTRACTION_MODEL, temperature: float = 0.1):
    """
    Punto único de comunicación con LLMs.
    Toda llamada pasa por aquí — nunca se llama directamente al SDK del proveedor.
    """
    response = await completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,  # Mínima para reproducibilidad (ADR-004)
        fallbacks=[FALLBACK_MODEL],
    )
    return response.choices[0].message.content
```

---

### D-06 — LLMs: Gemini 2.5 Flash (principal) + Groq (secundario)

**Razón:** Ambos 100% gratuitos. Gemini 2.5 Flash tiene ventana de contexto de 1M tokens (permite meter documentos completos sin chunking). Groq ofrece inferencia ultra-rápida para tareas simples.

**Límites del free tier:**

| Proveedor | Modelo | RPM | TPM | RPD |
|-----------|--------|-----|-----|-----|
| Gemini | 2.5 Flash | 10 | 250K | 500 |
| Gemini | 2.5 Pro | 5 | 250K | 25 |
| Groq | Llama 3.3 70B | 30 | 14.4K | 14.4K |
| Groq | Llama 3.1 8B | 30 | 20K | 14.4K |

**Implicación para el MVP:** Con 500 requests/día en Gemini y 14.4K en Groq, el MVP puede procesar decenas de documentos por día sin costo. Suficiente para hackathon y validación temprana.

**Alternativas descartadas:**
- OpenAI (GPT-4o-mini): no tiene free tier real.
- Anthropic (Claude): no tiene free tier para API.
- Cerebras: free tier disponible pero menos documentado, se mantiene como opción futura.

---

### D-07 — Deploy: Render (backend) + Vercel (frontend)

**Razón:** Ambos ofrecen free tier con autodeploy desde GitHub. Sin configuración de infraestructura. El workflow es: `git push` → deploy automático.

**Render free tier (backend):**
- 750 horas/mes de compute
- Sleep después de 15 min de inactividad (se despierta en ~30s al recibir request)
- Suficiente para MVP/demo

**Vercel free tier (frontend):**
- Deploys ilimitados
- 100 GB bandwidth/mes
- Serverless functions si se necesitan

**Alternativas consideradas:**
- Railway: similar a Render, ligeramente menos free tier.
- Fly.io: más complejo de configurar, mejor para apps con estado.

---

### D-08 — Sin Docker

**Razón:** El equipo no tiene experiencia con Docker más allá de correr servicios pre-configurados (Supabase local, n8n). La base de datos es cloud (Supabase), los LLMs son APIs, el deploy lo maneja Render/Vercel. Docker no agrega valor aquí y sí agrega complejidad.

**Cuándo reconsiderar:** Si el equipo crece, si se necesitan servicios adicionales locales, o si el deploy requiere control fino del entorno.

---

### D-09 — Parsing de documentos: PyMuPDF para PDF

**Razón:** Gratuito (AGPL para open source), rápido, buena extracción de texto con estructura (bloques, páginas). No requiere servicios externos ni OCR.

**Pipeline de ingesta conceptual:**

```python
# src/backend/ingestion/parsers.py
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class StructuredText:
    """Representación intermedia — output de la ingesta, input del análisis."""
    content: str           # Texto completo normalizado
    sections: list[dict]   # Secciones con título y contenido
    metadata: dict         # Formato original, páginas, idioma detectado, etc.


class DocumentParser(ABC):
    """Contrato que cumple cada adaptador de formato (ADR-003: ingesta desacoplada)."""

    @abstractmethod
    async def parse(self, file_content: bytes, filename: str) -> StructuredText:
        ...

    @abstractmethod
    def supports(self, filename: str) -> bool:
        ...


class MarkdownParser(DocumentParser):
    """Parser para .md — trivial, el contenido ya es texto estructurado."""

    def supports(self, filename: str) -> bool:
        return filename.lower().endswith('.md')

    async def parse(self, file_content: bytes, filename: str) -> StructuredText:
        text = file_content.decode('utf-8')
        sections = self._extract_sections(text)
        return StructuredText(
            content=text,
            sections=sections,
            metadata={"format": "markdown", "encoding": "utf-8"}
        )

    def _extract_sections(self, text: str) -> list[dict]:
        # Divide por headings de Markdown
        ...


class PDFParser(DocumentParser):
    """Parser para .pdf — extrae texto con PyMuPDF."""

    def supports(self, filename: str) -> bool:
        return filename.lower().endswith('.pdf')

    async def parse(self, file_content: bytes, filename: str) -> StructuredText:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=file_content, filetype="pdf")
        sections = []
        full_text = ""

        for page_num, page in enumerate(doc):
            page_text = page.get_text("text")
            full_text += page_text + "\n"
            sections.append({
                "title": f"Página {page_num + 1}",
                "content": page_text,
                "page": page_num + 1
            })

        return StructuredText(
            content=full_text,
            sections=sections,
            metadata={"format": "pdf", "pages": len(doc)}
        )


class PlainTextParser(DocumentParser):
    """Parser para .txt — el más simple posible."""

    def supports(self, filename: str) -> bool:
        return filename.lower().endswith('.txt')

    async def parse(self, file_content: bytes, filename: str) -> StructuredText:
        text = file_content.decode('utf-8')
        return StructuredText(
            content=text,
            sections=[{"title": "Documento completo", "content": text}],
            metadata={"format": "plaintext", "encoding": "utf-8"}
        )
```

---

### D-10 — Knowledge Model como Pydantic models

**Razón:** Pydantic define schemas validables que se serializan a JSON (para Supabase `jsonb`) y generan JSON Schema (para documentación). Un solo lugar define la estructura del Knowledge Model.

```python
# src/shared/models/knowledge_model.py
from pydantic import BaseModel
from typing import Optional


class SourceRef(BaseModel):
    """Referencia de evidencia flexible (ADR-004)."""
    document_id: str
    page: Optional[int] = None
    section: Optional[str] = None
    chunk_id: Optional[str] = None
    evidence: str  # Texto span del documento fuente
    verified: bool = False  # Si la evidencia fue verificada contra el documento


class Relation(BaseModel):
    """Relación entre elementos del Knowledge Model (ADR-006)."""
    target_id: str
    type: str  # constrains, participates_in, depends_on, contradicts
    description: Optional[str] = None


class KnowledgeElement(BaseModel):
    """Elemento tipado del Knowledge Model (ADR-002)."""
    id: str
    type: str  # proposito, concepto, actor, regla, proceso, restriccion
    name: str
    description: str
    source_ref: SourceRef
    relations: list[Relation] = []


class Inconsistency(BaseModel):
    """Inconsistencia detectada en el documento."""
    id: str
    description: str
    severity: str  # high, medium, low
    elements_involved: list[str]  # IDs de elementos relacionados
    source_ref: SourceRef


class MissingElement(BaseModel):
    """Información faltante según el esquema del tipo de documento."""
    id: str
    expected_element: str
    description: str
    importance: str  # high, medium, low


class Suggestion(BaseModel):
    """Sugerencia de mejora para el documento."""
    id: str
    description: str
    related_elements: list[str] = []
    source_ref: Optional[SourceRef] = None


class QualityAnalysis(BaseModel):
    """Resultado del análisis de calidad (ADR-001 capacidades 2-4)."""
    inconsistencies: list[Inconsistency] = []
    missing_elements: list[MissingElement] = []
    suggestions: list[Suggestion] = []


class KnowledgeModel(BaseModel):
    """Modelo completo de conocimiento extraído de un documento."""
    document_id: str
    document_type: str  # prd, technical_spec, policy_process, generic
    document_type_confirmed: bool = False
    language: str  # es, en
    elements: list[KnowledgeElement] = []
    quality_analysis: QualityAnalysis = QualityAnalysis()
    prompt_version: str  # Versión del prompt usado (ADR-004: reproducibilidad)
    model_version: str  # Versión del modelo usado
```

---

## Decisiones pendientes (a resolver durante implementación)

| # | Decisión pendiente | Cuándo resolverla | Impacto |
|---|---|---|---|
| P-01 | Estructura exacta de tablas en Supabase (RLS policies, índices) | Al crear el primer spec de backend | Bajo |
| P-02 | Formato exacto de prompts para extracción del KM | Al implementar el motor de análisis | Medio |
| P-03 | Si inferencia de tipo y extracción ocurren en 1 o 2 llamadas al LLM | Al implementar, se prueba ambos | Bajo |
| P-04 | Diseño de componentes UI (layout, navegación, presentación del KM) | Al crear el spec de frontend | Medio |
| P-05 | Estrategia de chunking si un documento excede el contexto del modelo secundario (Groq 128K) | Al probar con documentos grandes | Bajo (Gemini tiene 1M) |
| P-06 | Manejo de rate limits en producción (cola, retry, backoff) | Post-hackathon si hay usuarios concurrentes | Bajo para MVP |
| P-07 | Autenticación de usuarios | Post-MVP o si se necesita antes del demo | Bajo para hackathon |

---

## Diagrama de flujo del sistema

```
Usuario
  │
  ├─ Carga documento (.md, .txt, .pdf)
  │
  ▼
┌─────────────────────────────────────────────────────────┐
│ Frontend (React + TS + Vite)                            │
│                                                         │
│  Upload → Consentimiento → Tipo (confirmar) → Viewer   │
└────────────────────────┬────────────────────────────────┘
                         │ REST API
                         ▼
┌─────────────────────────────────────────────────────────┐
│ Backend (FastAPI + Python)                              │
│                                                         │
│  1. Ingesta (parser según formato)                      │
│     └─ Output: StructuredText                           │
│                                                         │
│  2. Clasificación de tipo (LLM via LiteLLM)             │
│     └─ Output: tipo sugerido → usuario confirma         │
│                                                         │
│  3. Extracción del Knowledge Model (LLM via LiteLLM)    │
│     └─ Output: KnowledgeModel (Pydantic)                │
│                                                         │
│  4. Verificación de evidencia                           │
│     └─ Marca source_refs como verified/not-verified     │
│                                                         │
│  5. Análisis de calidad (LLM via LiteLLM)               │
│     └─ Output: QualityAnalysis                          │
│                                                         │
│  6. Persistencia (Supabase)                             │
│     └─ Guarda KM + QualityAnalysis como JSONB           │
│                                                         │
│  7. Q&A por lenguaje natural (LLM via LiteLLM)          │
│     └─ Sobre el KM generado, con evidencia trazable     │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ Servicios externos                                      │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ Gemini 2.5  │  │ Groq         │  │ Supabase      │  │
│  │ Flash       │  │ Llama 3.3/8B │  │ PostgreSQL    │  │
│  │ (principal) │  │ (secundario) │  │ (persistencia)│  │
│  └─────────────┘  └──────────────┘  └───────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## Evolución a producción

Cuando el proyecto supere las limitaciones del free tier:

| Cambio | De | A | Esfuerzo |
|---|---|---|---|
| DB | Supabase free | Supabase Pro ($25/mes) | Config change |
| LLM | Gemini free | Gemini pay-as-you-go | Config change |
| Backend | Render free (sleep) | Render paid (always on) | Config change |
| Auth | Sin auth | Supabase Auth | Medio (agregar middleware) |
| Cache | Sin cache | Redis (Upstash free tier) | Medio |
| Monitoring | Sin monitoring | Sentry free tier | Bajo |

Ningún cambio requiere reescribir la aplicación. La arquitectura está diseñada para escalar incrementalmente.
