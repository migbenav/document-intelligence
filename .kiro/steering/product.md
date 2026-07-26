---
inclusion: auto
---

# Product Context — Document Intelligence

## Propósito

Document Intelligence permite **comprender la estructura y contenido de un documento sin leerlo completo**, mediante un análisis progresivo que preserva la organización del documento y permite profundizar bajo demanda. No genera texto; guarda el entendimiento estructural para uso futuro.

## Usuarios objetivo

- Equipos legales y de compliance
- Equipos de documentación
- Product Managers
- Business Analysts
- Organizaciones con múltiples documentos relacionados (políticas, reglamentos, manuales, procedimientos)

## Alcance del MVP

El MVP trabaja con un único documento y produce:

1. **Análisis base automático** (< 5 segundos): ficha del documento con título, resumen, clasificación, estadísticas y estructura detectada.
2. **Análisis bajo demanda** (el usuario elige): construir/revisar índice, relaciones entre secciones, preguntas que responde el documento, conclusiones y recomendaciones.
3. **Análisis a nivel de bloque** (para documentos con estructura): rol del bloque, relaciones del bloque.
4. **Configuración del LLM**: selector de modelo, auto-fallback configurable.
5. **Persistencia**: resultados guardados, detección de cambios por metadatos.
6. **Trust by Evidence**: cada resultado trazable al texto fuente.

## Capacidades del MVP

| Capacidad | Descripción |
|-----------|-------------|
| C1. Ingreso | Carga de documentos (MD, TXT, PDF) con consentimiento previo |
| C2. Análisis base | Ficha automática en < 5s: resumen, clasificación, estadísticas, estructura |
| C3. Análisis bajo demanda | Índice, relaciones, preguntas, conclusiones — acumulativos |
| C4. Análisis de bloque | Rol y relaciones a nivel de bloque (solo docs con estructura) |
| C5. Configuración LLM | Selector de modelo + auto-fallback configurable |
| C6. Persistencia | Resultados guardados, detección de cambios por metadatos |
| C7. Trust by Evidence | source_ref en cada resultado |
| C8. Privacidad | Consentimiento, minimización, abstracción del proveedor |

## Clasificación de documentos

La clasificación es funcional (orienta qué análisis es útil), no tipológica:

- Normativo (reglamento, ley, política)
- Procedimental (manual, guía, SOP)
- Técnico (spec, arquitectura)
- Narrativo / sin estructura (artículo, cuento, reporte)

Documentos narrativos obtienen solo análisis base + "Preguntas que responde" + "Conclusiones". Los análisis de nivel bloque no se ofrecen para ellos.

## Diferenciador

Este producto NO es un chatbot sobre documentos ni un generador de resúmenes. ES una herramienta que guarda el conocimiento estructural de un documento, permite entender sin leer y profundizar bajo demanda, y prepara el terreno para sincronización entre documentos en futuras versiones.

## Principios funcionales

- El objetivo es ayudar al usuario a comprender el documento sin leerlo.
- Análisis progresivo: una primera salida rápida y opciones de profundización bajo demanda.
- La estructura del documento se preserva como árbol jerárquico de bloques.
- Todo resultado debe poder verificarse trazándolo hasta el documento original.
- El sistema informa y pide consentimiento antes de procesar datos externamente.
- Documentos sin estructura definida obtienen valor limitado pero real (análisis base).
- El usuario tiene control sobre qué se analiza y con qué modelo.

## Funcionalidades fuera del alcance del MVP

No implementar:

- Análisis multi-documento ni relaciones entre documentos.
- Modificación/corrección del documento basada en análisis.
- Sugerencias de texto actualizado.
- Knowledge Graph completo (motor de grafos dedicado).
- Procesamiento local o self-hosted de IA.
- Edición colaborativa, control de versiones documental.
- DOCX, OCR, imágenes, tablas complejas.
- Confidence scores por resultado.
- Detección de cambios por content hash (solo metadatos en MVP).
- Configuración dinámica de taxonomías o tipos personalizados.

## Documentación de referencia

- Visión del producto: #[[file:docs/product/01-product-vision.md]]
- Problem Discovery: #[[file:docs/product/02-problem-discovery.md]]
- PRD v2 (vigente): #[[file:docs/product/03-prd v2.md]]
- PRD v0.6 (superseded): #[[file:docs/product/03-prd.md]]
- Spec MVP original: #[[file:docs/product/04-product-mvp-specification.md]]
- ADR-007 Rediseño estructural: #[[file:docs/decisions/ADR-007-structural-analysis-redesign.md]]
- Retrospectiva 001: #[[file:docs/retrospectives/001-knowledge-model-disconnect.md]]
