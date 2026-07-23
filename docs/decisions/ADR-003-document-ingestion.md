# ADR-003 — Restricciones de ingesta de documentos

> Estado: **Accepted**
> Fecha: 2026-07-23
> Aprobada: 2026-07-23
> Depende de: ADR-001-mvp-scope.md (aprobada), ADR-002-knowledge-model.md (aprobada)

---

# Contexto

La ADR-001 estableció que el MVP trabaja con un único documento por análisis. La ADR-002 definió que el resultado del análisis es un Knowledge Model (elementos tipados con relaciones opcionales). Sin embargo, ningún documento del proyecto especifica qué entra al sistema: qué formatos se aceptan, qué tamaño máximo se permite, qué encoding se soporta ni en qué idiomas funciona el análisis.

**OBS-04 — No se especifican formatos de documento soportados, tamaño máximo, encoding ni idiomas**

RF-01 dice "el sistema debe permitir cargar un documento" sin ninguna restricción. Cada formato implica un pipeline de ingesta diferente (parser, extracción de texto, manejo de estructura) y afecta decisiones de arquitectura. Sin definir estos límites no se puede dimensionar el sistema ni diseñar el componente de ingesta.

---

# Problema

¿Qué tipos de documentos debe soportar el MVP y cuáles son las restricciones de ingesta?

Específicamente:

1. ¿Qué formatos de archivo se aceptan?
2. ¿Cuál es el tamaño máximo de documento?
3. ¿Qué encoding se soporta?
4. ¿En qué idiomas funciona el análisis?
5. ¿Se soportan documentos con imágenes, tablas u otros elementos no textuales?

---

# Alternativas consideradas

---

## Alternativa 1 — Solo Markdown

**Descripción**

El MVP acepta únicamente documentos en formato Markdown (.md). Es el formato más simple de procesar: texto plano con estructura semántica (encabezados, listas, bloques de código). No requiere parsing binario ni dependencias externas para extraer el texto.

Restricciones propuestas:

- Formato: Markdown (.md)
- Tamaño máximo: 100 KB (~25.000 palabras)
- Encoding: UTF-8
- Idiomas: español e inglés
- Elementos no textuales: se ignoran imágenes embebidas; tablas Markdown se procesan como texto

**Ventajas**

- Pipeline de ingesta trivial: el archivo ya es texto estructurado.
- Sin dependencias de parsing externo (no se necesita PDF parser, DOCX unzip, etc.).
- La estructura del Markdown (headings, listas) facilita la segmentación para el LLM.
- Ideal para el tipo de documentos del dominio objetivo (PRDs, specs, documentación técnica).
- Máximo control sobre qué entra al sistema: si es Markdown, el contenido es predecible.

**Desventajas**

- Excluye a usuarios cuya documentación está en PDF, Word o wikis.
- Limita la demostración del MVP a un nicho técnico que ya usa Markdown.
- No valida la capacidad del sistema de manejar documentos "del mundo real" (contratos, políticas, manuales en PDF/DOCX).

**Impacto técnico**

Mínimo. No requiere librerías de parsing. El texto se pasa directamente al LLM con segmentación por headers.

**Impacto en evolución futura**

Bajo impacto en la arquitectura futura. Agregar nuevos formatos implica agregar adaptadores de parsing que convierten a una representación intermedia de texto. Si el sistema se diseña con una capa de abstracción "document → plain text with structure", escalar a otros formatos es modular.

---

## Alternativa 2 — Markdown + texto plano + PDF

**Descripción**

El MVP acepta tres formatos: Markdown (.md), texto plano (.txt) y PDF (.pdf). Cubre documentación técnica y documentos empresariales básicos. PDF se procesa con extracción de texto (sin OCR de imágenes).

Restricciones propuestas:

- Formatos: Markdown (.md), texto plano (.txt), PDF (.pdf)
- Tamaño máximo: 200 KB para Markdown/texto, 5 MB para PDF (equivalente a ~50 páginas con texto)
- Encoding: UTF-8 para Markdown/texto; encoding nativo para PDF
- Idiomas: español e inglés
- Elementos no textuales: se extrae solo el texto de PDFs; imágenes, gráficos y formularios se ignoran; tablas se extraen como texto cuando es posible

**Ventajas**

- Cubre los dos extremos más comunes: documentación técnica (Markdown) y documentos de negocio (PDF).
- PDF es el formato universal para documentos formales (políticas, contratos, specs externas).
- Permite validar la hipótesis con documentos que el usuario típico ya tiene disponibles.
- El texto plano es trivial de procesar y amplía la base sin costo.

**Desventajas**

- La extracción de texto desde PDF introduce una dependencia de parsing y puede producir resultados de calidad variable (layout complejo, columnas, headers/footers repetidos).
- Los PDFs escaneados (imagen) no son procesables sin OCR, que queda fuera del alcance.
- Mayor superficie de errores: un PDF mal formado puede producir texto ilegible que afecte la calidad del Knowledge Model.
- Se necesita validación de que el texto extraído del PDF es coherente antes de enviarlo al LLM.

**Impacto técnico**

Medio. Requiere una librería de extracción de texto desde PDF. Introduce la necesidad de una capa de normalización que unifique la salida de distintos parsers antes de enviar al LLM.

**Impacto en evolución futura**

Medio. La capa de normalización creada para soportar PDF es reutilizable para agregar DOCX, HTML u otros formatos. Establece el patrón "adaptador → texto normalizado → análisis".

---

## Alternativa 3 — Markdown + texto plano + PDF + DOCX

**Descripción**

El MVP acepta cuatro formatos: Markdown, texto plano, PDF y DOCX. Cubre el espectro completo de documentos técnicos y empresariales sin requerir que el usuario convierta sus archivos.

Restricciones propuestas:

- Formatos: Markdown (.md), texto plano (.txt), PDF (.pdf), Word (.docx)
- Tamaño máximo: 200 KB para Markdown/texto, 5 MB para PDF, 5 MB para DOCX
- Encoding: UTF-8 para Markdown/texto; nativo para PDF/DOCX
- Idiomas: español e inglés
- Elementos no textuales: se extrae solo el texto; imágenes, gráficos, comentarios y track changes se ignoran; tablas se extraen como texto cuando es posible

**Ventajas**

- Máxima cobertura de formatos comunes sin entrar en formatos exóticos.
- DOCX es el formato más usado en entornos empresariales (políticas, requisitos, manuales).
- Reduce la fricción para el usuario: no necesita convertir su documento antes de analizarlo.
- Permite validar la hipótesis con los documentos que los usuarios realmente tienen.

**Desventajas**

- Cuatro parsers distintos a mantener y testear.
- DOCX puede contener macros, OLE objects, revisiones y otros elementos complejos que deben ignorarse de forma segura.
- Mayor superficie de bugs en la ingesta.
- El esfuerzo de ingeniería en parsing no aporta valor directo a la validación de la hipótesis (el diferenciador es el análisis, no la ingesta).
- Riesgo de diluir el esfuerzo del MVP en problemas de compatibilidad de formatos.

**Impacto técnico**

Medio-alto. Requiere dos librerías de parsing (PDF y DOCX), una capa de normalización robusta, y manejo de errores para documentos malformados en cada formato.

**Impacto en evolución futura**

Alto. El patrón de adaptadores está completamente establecido. Agregar HTML, ODT u otros formatos es incremental.

---

# Consideraciones transversales

## Sobre el tamaño máximo

El tamaño máximo debe acotarse no solo por almacenamiento sino por la ventana de contexto del LLM. Un documento de 100 KB de Markdown equivale a ~25.000 palabras (~33.000 tokens). Documentos que excedan la ventana de contexto requerirán estrategias de chunking que afectan la calidad del análisis.

Para el MVP, es preferible trabajar con documentos que quepan razonablemente en una sola pasada de análisis (con segmentación por secciones) antes de implementar estrategias de chunking avanzadas.

## Sobre el idioma

Los LLMs actuales funcionan razonablemente bien en español e inglés. Soportar ambos idiomas no requiere ingeniería adicional significativa (el LLM los maneja de forma nativa). Otros idiomas podrían funcionar pero no se garantizan.

## Sobre encoding

UTF-8 cubre la inmensa mayoría de documentos modernos. Los PDFs manejan su propio encoding internamente. Aceptar solo UTF-8 para texto plano y Markdown es una restricción razonable que evita problemas de conversión.

---

# Recomendación

**Alternativa 2 — Markdown + texto plano + PDF**, con una capa de ingesta desacoplada del análisis.

**Razonamiento:**

1. **Cobertura práctica sin complejidad excesiva.** Markdown y texto plano cubren documentación técnica; PDF cubre documentos de negocio. Juntos permiten validar la hipótesis con los documentos que los usuarios ya tienen.

2. **La decisión arquitectónica clave es el desacoplamiento.** La capa de ingesta se diseña como un módulo independiente que convierte cualquier formato soportado a una representación intermedia de texto estructurado. El motor de análisis (que genera el Knowledge Model) opera sobre esa representación, no sobre el formato original.

3. **PDF amplía la base de usuarios sin comprometer el foco.** Muchos documentos empresariales formales solo existen en PDF. Excluirlo limita la validación con usuarios reales de negocio.

4. **Los límites de tamaño ajustados (1 MB para texto, 10 MB para PDF) permiten documentos reales** sin abrir la puerta a archivos gigantes que excedan la capacidad de procesamiento del MVP.

5. **La arquitectura desacoplada permite agregar DOCX u otros formatos como adaptadores nuevos**, sin modificar el motor de análisis ni el modelo de conocimiento.

---

# Decisión final

**Decisión aprobada: Alternativa 2 — Markdown + texto plano + PDF, con capa de ingesta desacoplada.**

## Principio arquitectónico

La capa de ingesta es un módulo independiente y desacoplado del motor de análisis. Su responsabilidad es transformar el documento original en una representación intermedia de texto estructurado. El motor de análisis que genera el Knowledge Model opera exclusivamente sobre esa representación intermedia, sin conocimiento del formato original.

Este desacoplamiento permite agregar nuevos formatos de entrada como adaptadores sin modificar el pipeline de análisis.

## Restricciones aprobadas

| Parámetro | Valor |
|-----------|-------|
| Formatos | Markdown (.md), texto plano (.txt), PDF (.pdf) |
| Tamaño máximo (Markdown/TXT) | 1 MB |
| Tamaño máximo (PDF) | 10 MB |
| Encoding (Markdown/TXT) | UTF-8 |
| Encoding (PDF) | Nativo del formato |
| Idiomas | Español e inglés |
| Elementos no textuales | Imágenes se ignoran; tablas simples se extraen como texto; tablas complejas se ignoran |
| PDF escaneados | No soportados (sin OCR) |

## Fuera del alcance del MVP

- DOCX.
- OCR (PDFs escaneados).
- Procesamiento de imágenes.
- Tablas complejas (multi-nivel, celdas combinadas).

## Implicaciones para la especificación

Los documentos afectados deben actualizarse:

- `.specs/001-foundation/spec.md` — agregar restricciones de formato, tamaño, encoding e idiomas en RF-01 y en la sección de Restricciones; documentar el principio de capa de ingesta desacoplada.
- `docs/product/03-prd.md` — especificar en C1 qué formatos acepta el MVP y las exclusiones.
