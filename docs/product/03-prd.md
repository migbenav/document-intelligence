# Product Requirements Document

> Version: 0.5
> Decisiones aplicadas: ADR-001-mvp-scope.md, ADR-002-knowledge-model.md, ADR-003-document-ingestion.md, ADR-004-reliability-trust-model.md, ADR-005-privacy-external-processing.md

---

# Objetivo

> Decisión documentada en: decisions/ADR-001-mvp-scope.md

Construir un MVP de una plataforma de inteligencia documental que permita transformar un documento complejo en un Knowledge Model (modelo de conocimiento estructurado) que pueda ser analizado y consultado mediante inteligencia artificial.

El MVP debe demostrar que un documento puede ser comprendido más allá de su contenido textual, identificando elementos relevantes, inconsistencias internas, información faltante y oportunidades de mejora.

---

# Usuario objetivo

Personas y equipos que trabajan con documentación compleja y necesitan crear, revisar o mantener conocimiento estructurado.

Ejemplos:

- Product Managers.
- Business Analysts.
- Software Architects.
- Equipos técnicos.
- Organizaciones con múltiples documentos relacionados.

---

# Caso de uso principal

Un usuario carga un documento complejo.

El sistema analiza su contenido y genera una representación estructurada que permite:

- entender el propósito del documento;
- identificar conceptos importantes;
- encontrar reglas y restricciones;
- detectar inconsistencias internas (contradicciones y ambigüedades);
- identificar información faltante según la estructura esperada;
- obtener sugerencias de mejora;
- consultar información mediante IA.

---

# Capacidades del MVP

## C1. Ingreso de documentos

El usuario puede proporcionar documentos para análisis.

Formatos soportados en el MVP:

- Markdown (.md)
- Texto plano (.txt)
- PDF (.pdf)

Restricciones:

- Tamaño máximo: 1 MB (Markdown/TXT), 10 MB (PDF).
- Encoding: UTF-8 para Markdown y texto plano; nativo para PDF.
- Idiomas: español e inglés.
- Imágenes: se ignoran.
- Tablas simples: se extraen como texto. Tablas complejas: se ignoran.
- PDFs escaneados (imagen): no soportados (sin OCR).

La capa de ingesta es un módulo desacoplado del motor de análisis. Su responsabilidad es transformar el documento original en una representación intermedia de texto estructurado sobre la cual opera el análisis.

Resultado esperado:

El sistema procesa el documento y genera un Knowledge Model: una representación interna estructurada con elementos tipados y relaciones opcionales entre ellos.

---

## C2. Comprensión documental

El sistema construye un Knowledge Model identificando los siguientes elementos (taxonomía fija en el MVP):

- propósito;
- conceptos;
- actores;
- reglas;
- procesos;
- restricciones.

Cada elemento incluye un tipo, contenido textual y una referencia de evidencia trazable (`source_ref`) que permite verificar su origen en el documento fuente. Las relaciones entre elementos se capturan de forma opcional cuando el sistema las identifica con suficiente confianza.

---

## C3. Exploración del conocimiento

El usuario puede visualizar y consultar el Knowledge Model generado.

Ejemplos:

- ¿Cuál es el objetivo de este documento?
- ¿Qué reglas define?
- ¿Quiénes participan?
- ¿Qué conceptos son importantes?
- ¿Qué relaciones existen entre los elementos?

---

## C4. Análisis de calidad documental

El sistema evalúa la calidad del documento basándose en el Knowledge Model generado:

- detecta inconsistencias internas: contradicciones y ambigüedades dentro del documento;
- identifica información faltante según la estructura esperada para el tipo de documento;
- genera sugerencias de mejora.

---

## C5. Asistencia mediante IA

El usuario puede interactuar con el Knowledge Model utilizando lenguaje natural. Las respuestas incluyen evidencia trazable al documento original para que el usuario pueda verificar su corrección.

---

## C6. Modelo de confianza (Trust by Evidence)

El MVP proporciona transparencia y verificabilidad, no una garantía de precisión absoluta del LLM:

- Cada elemento del Knowledge Model incluye una referencia de evidencia (`source_ref`) que lo traza hasta el documento original.
- El sistema verifica que la evidencia referenciada existe realmente en el documento. Los elementos no-verificables se señalan.
- El sistema usa parámetros de generación controlados, tracking de versión del modelo y prompts versionados para maximizar consistencia entre ejecuciones (reproducibilidad acotada a estructura y hallazgos principales, no texto idéntico).

El MVP no garantiza que el LLM sea correcto el 100% del tiempo. Garantiza que el usuario puede verificar todo resultado.

---

## C7. Privacidad y procesamiento de datos

El MVP procesa documentos mediante un servicio externo de IA. El sistema opera bajo los siguientes principios de privacidad:

- **Transparencia:** El usuario es informado, antes de iniciar el análisis, de que el contenido del documento será procesado por un servicio externo de IA.
- **Consentimiento:** El usuario debe autorizar explícitamente el procesamiento. Sin consentimiento, no se realiza el análisis.
- **Minimización:** Solo se envía al servicio de IA la información estrictamente necesaria para el análisis (texto del documento y prompts del sistema).
- **Retención limitada:** El contenido del documento original no se retiene más allá de lo operativamente necesario para completar el análisis y permitir la interacción durante la sesión.
- **Abstracción del proveedor:** La arquitectura incluye una capa de abstracción que permite reemplazar el backend de procesamiento de IA sin modificar el pipeline de análisis, habilitando opciones de procesamiento local o self-hosted en iteraciones futuras.

---

# Fuera de alcance

El MVP no incluirá:

- Knowledge Graph completo (motor de grafos dedicado);
- análisis multi-documento ni relaciones entre documentos;
- configuración dinámica de taxonomías;
- detección de inconsistencias entre documentos relacionados;
- análisis de impacto de cambios entre documentos;
- formato DOCX;
- OCR para PDFs escaneados;
- procesamiento de imágenes dentro de documentos;
- tablas complejas (multi-nivel, celdas combinadas);
- garantía de precisión del 100% del LLM;
- edición directa del Knowledge Model por el usuario;
- fine-tuning del modelo basado en feedback;
- framework de evaluación completo;
- procesamiento local o self-hosted de IA;
- selección de proveedor de IA por parte del usuario;
- cumplimiento de regulaciones específicas de industria;
- auditoría detallada de acceso a datos;
- edición colaborativa;
- control documental empresarial;
- gestión avanzada de permisos;
- flujos de aprobación;
- integración con sistemas externos;
- sincronización automática entre múltiples repositorios.

---

# Criterios de éxito

El MVP será exitoso si demuestra que:

- un usuario puede comprender un documento complejo más rápido;
- la IA puede explicar el contenido basado en conocimiento extraído, con evidencia trazable al documento original;
- se pueden identificar inconsistencias internas que serían difíciles de encontrar manualmente;
- el sistema detecta información faltante relevante para el tipo de documento;
- las sugerencias de mejora aportan valor al usuario;
- el usuario puede verificar el origen de cada elemento del Knowledge Model mediante su referencia de evidencia.

---

# Flujo principal del usuario

1. El usuario ingresa un documento.

2. El sistema informa al usuario que el contenido será procesado por un servicio externo de IA.

3. El usuario da consentimiento explícito para el procesamiento.

4. El sistema analiza el contenido.

5. La IA identifica elementos relevantes:
   - propósito
   - conceptos
   - actores
   - reglas
   - procesos
   - restricciones

6. El sistema genera un Knowledge Model: elementos tipados con relaciones opcionales.

7. El sistema evalúa la calidad documental:
   - inconsistencias internas
   - información faltante según estructura esperada
   - sugerencias de mejora

8. El usuario puede explorar el conocimiento generado y los resultados del análisis de calidad.

9. El usuario puede realizar preguntas sobre el documento.

10. El sistema responde utilizando el conocimiento extraído.

---

# Prioridad del MVP

## Must Have

- Cargar documento.
- Analizar documento.
- Generar Knowledge Model (elementos tipados con relaciones opcionales).
- Incluir referencia de evidencia trazable (`source_ref`) en cada elemento.
- Verificar que la evidencia referenciada existe en el documento original.
- Detectar inconsistencias internas.
- Identificar información faltante según estructura esperada.
- Sugerir mejoras basadas en el Knowledge Model.
- Consultar mediante IA (respuestas con evidencia trazable).
- Mostrar resultados.
- Parámetros de generación controlados y prompts versionados.
- Informar al usuario sobre procesamiento externo antes del análisis.
- Consentimiento explícito del usuario para procesamiento externo.
- Enviar solo información mínima necesaria al servicio de IA.
- Retención del contenido limitada a lo operativamente necesario.
- Capa de abstracción del proveedor de IA.

## Should Have

- Mostrar relaciones internas entre conceptos del documento.
- Feedback pasivo: permitir al usuario marcar un elemento como incorrecto o irrelevante (sin edición directa del Knowledge Model ni mejora automática del sistema).
- Cifrado del documento en tránsito hacia el servicio de IA.

## Could Have

- Taxonomía configurable por tipo de documento.
- Exportar conocimiento extraído.

## Not Now

- Knowledge Graph completo (motor de grafos dedicado).
- Configuración dinámica de taxonomías.
- Análisis multi-documento.
- Relaciones entre documentos.
- Comparar documentos.
- Analizar impacto de cambios entre documentos.
- Confidence scores por elemento.
- Edición directa del Knowledge Model.
- Fine-tuning basado en feedback del usuario.
- Capa de validación completa.
- Procesamiento local o self-hosted de IA.
- Selección de proveedor de IA por el usuario.
- Cumplimiento de regulaciones específicas de industria.
- Colaboración.
- Control de versiones.
- Integraciones externas.