---
inclusion: auto
---

# Product Context — Document Intelligence

## Propósito

Document Intelligence transforma documentos en conocimiento estructurado para ayudar a comprenderlos, mantenerlos y evolucionarlos mediante inteligencia artificial. No genera texto; comprende el conocimiento contenido en documentos existentes.

## Usuarios objetivo

- Product Managers
- Business Analysts
- Software Architects
- Equipos técnicos
- Equipos de documentación

## Alcance del MVP

El MVP trabaja con un único documento y produce:

1. Extracción de conocimiento estructurado (Knowledge Model).
2. Detección de inconsistencias internas.
3. Identificación de información faltante según el tipo de documento.
4. Sugerencias de mejora.
5. Consulta por lenguaje natural con evidencia trazable.

## Tipos de documentos soportados

- PRD (Product Requirements Document)
- Technical Spec
- Policy / Process
- Generic (fallback sin evaluación de completitud)

El tipo se determina mediante inferencia automática + confirmación del usuario.

## Funcionalidades fuera del alcance del MVP

No implementar:

- Análisis multi-documento ni relaciones entre documentos.
- Knowledge Graph completo (motor de grafos dedicado).
- Configuración dinámica de taxonomías ni tipos personalizados.
- Vocabulario de relaciones extensible por el usuario.
- Esquemas específicos de dominio (legal, médico, financiero).
- Edición directa del Knowledge Model.
- Fine-tuning basado en feedback.
- Procesamiento local o self-hosted de IA.
- DOCX, OCR, imágenes, tablas complejas.
- Colaboración, control de versiones, integraciones externas.
- Garantía de precisión del 100% del LLM.
- Confidence scores por elemento.

## Principios funcionales

- El conocimiento es más importante que el documento.
- La IA asiste al usuario; no reemplaza su criterio.
- Todo resultado debe poder verificarse trazándolo hasta el documento original.
- La consistencia tiene prioridad sobre la generación de texto.
- El sistema informa y pide consentimiento antes de procesar datos externamente.
- Un documento sin tipo conocido sigue obteniendo valor (tipo Generic: todas las capacidades excepto evaluación de completitud).

## Documentación de referencia

- Visión del producto: #[[file:docs/product/01-product-vision.md]]
- Problem Discovery: #[[file:docs/product/02-problem-discovery.md]]
- PRD: #[[file:docs/product/03-prd.md]]
- Spec MVP: #[[file:docs/product/04-product-mvp-specification.md]]
