# Spec - Product Foundation

> Version: 0.3
> Decisiones aplicadas: ADR-001-mvp-scope.md, ADR-002-knowledge-model.md, ADR-003-document-ingestion.md

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

Para obtener respuestas basadas en el Knowledge Model generado.

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

Cada elemento incluye: tipo, nombre, contenido textual y referencia a su ubicación en el documento fuente.

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

El usuario podrá consultar el Knowledge Model mediante preguntas en lenguaje natural.

---

## RF-10

El sistema mostrará el Knowledge Model y los resultados del análisis de calidad de forma estructurada.

---

# Requisitos No Funcionales

- El análisis debe ser reproducible.
- La arquitectura debe permitir incorporar nuevos tipos de análisis.
- La solución debe ser modular.
- Debe ser posible reemplazar el proveedor del LLM sin modificar el resto del sistema.
- La capa de ingesta debe estar desacoplada del motor de análisis, permitiendo agregar nuevos formatos como adaptadores independientes.

---

# Criterios de Aceptación

## CA-01

Dado un documento válido

Cuando el usuario inicia el análisis

Entonces el sistema genera un Knowledge Model con elementos tipados según la taxonomía definida.

---

## CA-02

Dado un Knowledge Model generado

Cuando existen contradicciones o ambigüedades en el documento

Entonces el sistema las identifica y las presenta al usuario como inconsistencias internas.

---

## CA-03

Dado un Knowledge Model generado

Cuando el documento carece de elementos esperados según su tipo

Entonces el sistema identifica la información faltante.

---

## CA-04

Dado un Knowledge Model generado

Cuando el usuario realiza una pregunta

Entonces la respuesta utiliza el conocimiento del modelo.

---

## CA-05

El usuario puede visualizar los elementos del Knowledge Model y los resultados del análisis de calidad.

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