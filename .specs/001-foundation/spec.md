# Spec - Product Foundation

> Version: 0.4
> Decisiones aplicadas: ADR-001-mvp-scope.md, ADR-002-knowledge-model.md, ADR-003-document-ingestion.md, ADR-004-reliability-trust-model.md

---

# Objetivo

Implementar la primera capacidad funcional de Document Intelligence, permitiendo analizar un documento y transformarlo en un Knowledge Model (modelo de conocimiento estructurado con elementos tipados y relaciones opcionales) que pueda ser explorado y consultado por el usuario.

---

# Contexto

Esta Spec implementa el núcleo del MVP definido en el PRD.

Corresponde a la primera iteración del producto y busca validar la hipótesis principal:

"Un documento puede entenderse mejor cuando se representa como conocimiento estructurado en lugar de texto."

---

# Alcance

Esta iniciativa incluye:

- Ingreso de un documento.
- Análisis mediante IA.
- Generación del Knowledge Model (elementos tipados con relaciones opcionales).
- Análisis de calidad documental (inconsistencias internas, información faltante, sugerencias).
- Visualización de los resultados.
- Consulta mediante lenguaje natural.

No incluye:

- Knowledge Graph completo (motor de grafos dedicado).
- Análisis multi-documento ni relaciones entre documentos.
- Configuración dinámica de taxonomías.
- Formato DOCX, OCR, procesamiento de imágenes ni tablas complejas.
- Colaboración, sincronización entre documentos ni control de versiones.

---

# Historias de Usuario

### US-001

Como usuario

Quiero cargar un documento

Para que el sistema pueda analizar su contenido.

---

### US-002

Como usuario

Quiero que el sistema genere un Knowledge Model del documento

Para comprender su estructura de conocimiento (propósito, conceptos, actores, reglas, procesos, restricciones y sus relaciones).

---

### US-003

Como usuario

Quiero visualizar los elementos del Knowledge Model

Para explorar el conocimiento contenido en el documento.

---

### US-004

Como usuario

Quiero conocer las inconsistencias internas del documento

Para identificar contradicciones y ambigüedades antes de que generen problemas.

---

### US-005

Como usuario

Quiero saber qué información falta según la estructura esperada

Para completar el documento con los elementos necesarios.

---

### US-006

Como usuario

Quiero recibir sugerencias de mejora

Para mejorar la calidad del documento basándome en el conocimiento extraído.

---

### US-007

Como usuario

Quiero realizar preguntas sobre el documento

Para obtener respuestas basadas en el Knowledge Model generado, con evidencia trazable al documento original.

---

### US-008 (Should Have)

Como usuario

Quiero poder marcar un elemento del Knowledge Model como incorrecto o irrelevante

Para señalar resultados que no reflejan el contenido del documento.

Nota: el feedback no incluye edición directa del Knowledge Model, flujos de corrección manual ni mejora automática del sistema.

---

# Requisitos Funcionales

## RF-01

El sistema debe permitir cargar un documento en los siguientes formatos:

- Markdown (.md)
- Texto plano (.txt)
- PDF (.pdf)

Restricciones de ingesta:

- Tamaño máximo: 1 MB (Markdown/TXT), 10 MB (PDF).
- Encoding: UTF-8 para Markdown y texto plano; nativo para PDF.
- Idiomas soportados: español e inglés.
- Imágenes dentro del documento: se ignoran.
- Tablas simples: se extraen como texto. Tablas complejas: se ignoran.
- PDFs escaneados (imagen): no soportados.

La capa de ingesta es un módulo desacoplado del motor de análisis. Transforma el documento original en una representación intermedia de texto estructurado sobre la cual opera el resto del pipeline.

---

## RF-02

El sistema debe analizar automáticamente el contenido y generar un Knowledge Model.

---

## RF-03

El Knowledge Model debe contener elementos tipados con la siguiente taxonomía fija:

- propósito
- conceptos
- actores
- reglas
- procesos
- restricciones

Cada elemento incluye: tipo, nombre, contenido textual y una referencia de evidencia (`source_ref`) que permite trazar el elemento hasta el documento original.

---

## RF-03.1

Cada elemento del Knowledge Model debe incluir un campo `source_ref` (referencia de evidencia flexible) con la información disponible para su trazabilidad:

- **document_id:** identificador del documento analizado.
- **page:** número de página (cuando esté disponible, principalmente PDF).
- **section:** sección o capítulo (cuando esté disponible, principalmente Markdown headings).
- **chunk_id:** identificador del fragmento de texto procesado.
- **evidence:** texto span o extracto textual del documento fuente que respalda el elemento.

El formato de la referencia se adapta al tipo de documento de origen. No se asumen referencias basadas en líneas.

---

## RF-03.2

El sistema debe verificar que la evidencia referenciada en `source_ref` (campo `evidence`) existe realmente en el documento original. Si una referencia no puede ser verificada, el elemento se marca como no-verificado.

---

## RF-04

El Knowledge Model puede incluir relaciones opcionales entre elementos cuando el sistema las identifica con suficiente confianza.

---

## RF-05

El sistema debe detectar inconsistencias internas del documento (contradicciones y ambigüedades) basándose en el Knowledge Model.

---

## RF-06

El sistema debe identificar información faltante según la estructura esperada para el tipo de documento.

---

## RF-07

El sistema debe generar sugerencias de mejora basadas en el Knowledge Model y el análisis de calidad.

---

## RF-08

El sistema debe almacenar temporalmente el Knowledge Model y los resultados del análisis.

---

## RF-09

El usuario podrá consultar el Knowledge Model mediante preguntas en lenguaje natural. Las respuestas deben incluir evidencia trazable al documento original (source_ref).

---

## RF-10

El sistema mostrará el Knowledge Model y los resultados del análisis de calidad de forma estructurada.

---

# Requisitos No Funcionales

- **Reproducibilidad acotada:** El sistema usa parámetros de generación controlados (temperatura mínima cuando esté disponible), tracking fijo de versión del modelo, y prompts versionados para maximizar consistencia. Dado el mismo documento, la misma configuración del modelo y la misma versión de prompts, el sistema produce: los mismos elementos principales de conocimiento, los mismos hallazgos críticos y un Knowledge Model estructuralmente comparable. No se garantiza output textual idéntico.
- La arquitectura debe permitir incorporar nuevos tipos de análisis.
- La solución debe ser modular.
- Debe ser posible reemplazar el proveedor del LLM sin modificar el resto del sistema.
- La capa de ingesta debe estar desacoplada del motor de análisis, permitiendo agregar nuevos formatos como adaptadores independientes.
- **Trazabilidad de evidencia:** Todo elemento generado y toda respuesta a consultas debe poder trazarse hasta el documento original mediante `source_ref`.
- **Verificación de referencias:** El sistema verifica que la evidencia citada existe en el documento fuente como mecanismo de trust del MVP.

---

# Criterios de Aceptación

## CA-01

Dado un documento válido

Cuando el usuario inicia el análisis

Entonces el sistema genera un Knowledge Model con elementos tipados según la taxonomía definida, cada uno con una referencia de evidencia (`source_ref`) verificable contra el documento original.

---

## CA-02

Dado un Knowledge Model generado

Cuando existen contradicciones o ambigüedades en el documento

Entonces el sistema las identifica y las presenta al usuario como inconsistencias internas, con evidencia trazable.

---

## CA-03

Dado un Knowledge Model generado

Cuando el documento carece de elementos esperados según su tipo

Entonces el sistema identifica la información faltante.

---

## CA-04

Dado un Knowledge Model generado

Cuando el usuario realiza una pregunta

Entonces la respuesta utiliza el conocimiento del modelo e incluye evidencia trazable al documento fuente.

---

## CA-05

El usuario puede visualizar los elementos del Knowledge Model y los resultados del análisis de calidad.

---

## CA-06

Dado un elemento del Knowledge Model cuya evidencia no puede ser verificada en el documento original

Entonces el sistema marca el elemento como no-verificado.

---

# Restricciones

Para el MVP:

- Se analizará un único documento.
- Formatos soportados: Markdown (.md), texto plano (.txt), PDF (.pdf).
- Tamaño máximo: 1 MB (Markdown/TXT), 10 MB (PDF).
- Encoding: UTF-8 para Markdown/TXT; nativo para PDF.
- Idiomas: español e inglés.
- La taxonomía de elementos es fija (no configurable por el usuario).
- El Knowledge Model se almacena como elementos tipados con relaciones opcionales (no como Knowledge Graph completo).
- No se soporta DOCX, OCR, procesamiento de imágenes ni tablas complejas.
- No habrá autenticación.
- No existirá edición colaborativa.
- No se mantendrá historial de versiones.

---

# Non-goals del MVP

El MVP no intenta proporcionar:

- Garantía de precisión del 100% del LLM.
- Validación automatizada completa de todo el razonamiento.
- Capacidades de edición del Knowledge Model por el usuario.
- Fine-tuning del modelo basado en feedback del usuario.
- Framework de evaluación completo.
- Output textual idéntico entre ejecuciones (solo consistencia estructural).

El MVP se centra en transparencia y verificabilidad: todo resultado puede trazarse hasta el documento original para que el usuario evalúe su corrección.

---

# Riesgos

- El LLM podría interpretar incorrectamente ciertos documentos.
- Algunos dominios requerirán modelos especializados.
- La calidad del análisis dependerá de la estructura del documento.

---

# Preguntas abiertas

Estas preguntas deberán resolverse durante la etapa de diseño:

- ¿Será necesario utilizar RAG para la consulta por lenguaje natural?
- ¿Cuál es la duración del almacenamiento temporal del Knowledge Model?
- ¿Cómo se visualizará el Knowledge Model al usuario?
- ¿Qué tipos de relaciones se soportarán en el MVP?
- ¿Qué estructura de referencia define los "elementos esperados" por tipo de documento?
- ¿Cómo se presenta visualmente un elemento marcado como "no-verificado"?