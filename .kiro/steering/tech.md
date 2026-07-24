---
inclusion: auto
---

# Technical Context — Document Intelligence

## Stack tecnológico

No se ha seleccionado stack tecnológico todavía. Las decisiones de tecnología se tomarán durante la fase de diseño técnico. Este archivo se actualizará cuando se definan.

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

- El pipeline se comunica con el servicio de IA a través de una capa de abstracción del proveedor.
- El proveedor de IA debe ser reemplazable sin modificar el pipeline de análisis.
- Consentimiento explícito del usuario antes de enviar datos.
- Solo se envía texto del documento y prompts del sistema. No metadata del usuario, cuentas ni historial.
- Retención del documento original limitada a lo operativamente necesario para la sesión.

### Análisis de calidad (ADR-006)

- 4 tipos de documento: PRD, Technical Spec, Policy/Process, Generic.
- Selección híbrida: inferencia automática + confirmación del usuario.
- Esquemas fijos en MVP; estructura extensible para futuras versiones.
- Generic soporta todas las capacidades excepto evaluación de completitud basada en esquema.

## Restricciones técnicas permanentes

- No acoplar código a un proveedor de IA específico.
- No enviar metadata de usuario, información de cuenta ni historial al servicio de IA.
- No almacenar el documento original más allá de la sesión operativa.
- No asumir referencias basadas en líneas (los PDFs no tienen líneas estables).
- No implementar Knowledge Graph completo ni motor de grafos.
- No implementar lógica multi-documento.
- No implementar configuración dinámica de taxonomías o tipos de documentos.

## ADRs de referencia

- #[[file:docs/decisions/ADR-001-mvp-scope.md]]
- #[[file:docs/decisions/ADR-002-knowledge-model.md]]
- #[[file:docs/decisions/ADR-003-document-ingestion.md]]
- #[[file:docs/decisions/ADR-004-reliability-trust-model.md]]
- #[[file:docs/decisions/ADR-005-privacy-external-processing.md]]
- #[[file:docs/decisions/ADR-006-document-type-schemas.md]]
