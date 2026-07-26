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
| Visualización estructura | React Flow | latest |
| Estado | Zustand | latest |
| Testing | Vitest | latest |

### Infraestructura y servicios

| Componente | Tecnología | Tier |
|---|---|---|
| Base de datos | Supabase (PostgreSQL) | Free tier — cloud siempre |
| Storage temporal | Supabase Storage o filesystem del server | Free tier |
| LLM principal | Google Gemini 2.5 Flash | Free tier (500 req/día, 1M tokens/min) |
| LLM ligero | Groq (Llama 3.3 70B) | Free tier (30 req/min) |
| Deploy backend | Render | Free tier |
| Deploy frontend | Vercel | Free tier |
| CI/CD | GitHub Actions | Free (repo público) |
| Contenedores | No se usa Docker | — |

### Estrategia multi-modelo (LLM)

| Tarea | Modelo asignado | Razón |
|---|---|---|
| Análisis base (resumen + clasificación) | Groq Llama 3.3 70B (light) | Tarea corta, velocidad alta, cumple < 5s |
| Análisis bajo demanda (índice, relaciones, preguntas, conclusiones) | Gemini 2.5 Flash (primary) | Contexto 1M tokens, calidad alta para análisis profundo |
| Consulta por lenguaje natural (Q&A) | Gemini 2.5 Flash (primary) | Coherente con modelo guardado |
| Fallback general | Configurable por usuario | Si el modelo asignado falla, auto-fallback al otro (si activado) |

**Política de fallback:**
- El usuario configura si el auto-fallback está activado o desactivado.
- Si activado: fallo en modelo asignado → intento automático con el otro modelo → informar al usuario.
- Si desactivado: fallo → informar error → ofrecer reintentar o cambiar modelo manualmente.
- La preferencia es por sesión en el MVP.

Toda comunicación con LLMs pasa por LiteLLM. Cambiar modelo = cambiar config, no código.

## Entorno de desarrollo

- **Local:** Solo código y tests. No Docker, no servicios locales.
- **Base de datos:** Siempre Supabase cloud (free tier). Desarrollo y producción apuntan a la misma tecnología.
- **Backend local:** `uvicorn` o `fastapi dev` apuntando a Supabase cloud.
- **Frontend local:** `npm run dev` apuntando al backend local.
- **Deploy:** Autodeploy desde GitHub (Render para backend, Vercel para frontend).

## Principios arquitectónicos

Derivados de los ADR aprobados. Toda implementación debe respetar estos principios:

### Análisis progresivo (ADR-007)

- El objetivo del sistema NO es extraer entidades de un documento. Es ayudar al usuario a comprender el documento sin leerlo y guardar ese entendimiento.
- El análisis se divide en dos niveles: **base** (automático, rápido, < 5s) y **bajo demanda** (el usuario elige qué ejecutar).
- El análisis base combina procesamiento local (estadísticas, detección de estructura, título) con una llamada LLM corta (resumen + clasificación).
- Cada análisis bajo demanda es independiente, se ejecuta por separado, y su resultado se guarda como capa acumulativa.
- La estructura del documento se preserva como un **árbol jerárquico de bloques** con relaciones entre bloques.
- La clasificación del documento adapta el comportamiento de las opciones disponibles, no las bloquea.
- Si un análisis ya se ejecutó, no se re-ejecuta (salvo que el documento cambie).

### Modelo de estructura documental (ADR-007)

- El modelo central es `DocumentStructure`: ficha + árbol de estructura + análisis acumulativos.
- Vocabulario de relaciones: `constrains`, `depends_on`, `complements`, `contradicts`.
- Cada elemento tiene `source_ref` para trazabilidad (evidence).
- IDs únicos referenciables para cada nodo del árbol.

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

## Restricciones técnicas permanentes

- No acoplar código a un proveedor de IA específico (todo pasa por LiteLLM).
- No enviar metadata de usuario, información de cuenta ni historial al servicio de IA.
- No almacenar el documento original más allá de la sesión operativa.
- No asumir referencias basadas en líneas (los PDFs no tienen líneas estables).
- No implementar extracción de entidades tipadas como mecanismo de comprensión (la comprensión es estructural y progresiva, no una lista de entidades categorizadas).
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
- #[[file:docs/decisions/ADR-007-structural-analysis-redesign.md]]
- #[[file:docs/architecture/001-technology-stack.md]]
