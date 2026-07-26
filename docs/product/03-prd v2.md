# Product Requirements Document v2

> Version: 2.0
> Fecha: 2026-07-26
> Supersedes: PRD v0.6 (docs/product/03-prd.md)
> Decisiones aplicadas: ADR-001, ADR-003, ADR-004, ADR-005, ADR-007
> Motivado por: Retrospectiva 001

---

## Objetivo

Construir un MVP de una plataforma de inteligencia documental que permita **comprender la estructura y contenido de un documento sin leerlo completo**, mediante un análisis progresivo que preserve la organización del documento y permita profundizar bajo demanda.

El MVP debe demostrar que un usuario puede entender un documento complejo más rápidamente que leyéndolo, identificar su estructura, comprender el rol de sus partes, y guardar ese entendimiento para uso futuro.

---

## Diferenciador

Este producto NO es:
- Un chatbot sobre documentos (como NotebookLM o ChatPDF)
- Un generador de resúmenes (como herramientas de IA genéricas)
- Un editor de documentos

Este producto ES:
- Una herramienta que **guarda el conocimiento estructural** de un documento
- Que permite **entender sin leer** y **profundizar bajo demanda**
- Que prepara el terreno para **sincronización y alineación entre documentos** en futuras versiones

La finalidad no es hacer preguntas sobre un documento (eso lo hace cualquier IA). La finalidad es guardar la comprensión estructurada del documento para que cuando se agreguen más documentos, el sistema pueda detectar cómo se complementan, contradicen o dependen unos de otros.

---

## Usuario objetivo

Personas y equipos que trabajan con documentación normativa, regulatoria o procedimental compleja:

- Equipos legales y de compliance
- Equipos de documentación
- Product Managers
- Business Analysts
- Organizaciones con múltiples documentos relacionados (políticas, reglamentos, manuales, procedimientos)

La metodología funciona especialmente bien para documentos que necesitan mantener relación con otros documentos. Documentos sin estructura (artículos, cuentos, reportes) obtienen solo el análisis básico.

---

## Caso de uso principal

Un usuario carga un documento normativo o procedimental. En menos de 5 segundos obtiene una ficha que le dice:
- De qué trata el documento (resumen de 2-3 líneas)
- Qué tipo de documento es (normativo, guía, manual, etc.)
- Cómo está organizado (artículos, secciones, partes, etc.)
- Estadísticas básicas (páginas, secciones, niveles de jerarquía)

Luego, el usuario puede solicitar análisis más profundos:
- Construir/revisar el índice del documento
- Ver relaciones entre secciones
- Ver qué preguntas responde el documento
- Obtener recomendaciones estructurales

Cada análisis que se ejecuta se guarda. El usuario no necesita repetirlo.

---

## Capacidades del MVP

### C1. Ingreso de documentos

Sin cambios respecto a PRD v0.6. Formatos: Markdown, texto plano, PDF. Límites y restricciones se mantienen según ADR-003.

---

### C2. Análisis base (automático, rápido)

Al cargar un documento, el sistema produce automáticamente en < 5 segundos:

- **Título:** nombre del archivo y/o título extraído del contenido.
- **Resumen:** bloque de 2-3 líneas explicando de qué trata y cuál es su objetivo.
- **Clasificación:** qué tipo de documento es (normativo, guía, manual, procedimiento, técnico, narrativo, otro).
- **Estadísticas:** número de páginas, bloques/párrafos, secciones detectadas.
- **Tipo de organización:** si usa artículos, secciones numeradas, headings, u otra estructura. Niveles de jerarquía.
- **Presencia de índice:** si el documento ya contiene un índice.

Este análisis se ejecuta sin intervención del usuario y se guarda como la "ficha" del documento.

---

### C3. Análisis bajo demanda (opciones)

El usuario ve la ficha y puede solicitar análisis profundos. Cada uno es una acción independiente cuyos resultados se acumulan en el modelo guardado.

#### C3.1 Construir/revisar índice

El sistema analiza el documento y produce un árbol de estructura (secciones, subsecciones, bloques) donde cada nodo tiene:
- Título de la sección
- Nivel jerárquico
- Rol funcional (define términos, clasifica, establece procedimientos, lista normas, recomienda)
- Resumen breve

Si el documento ya tiene un índice, el sistema valida que refleje lo que realmente está escrito.

#### C3.2 Relaciones entre secciones

Identifica cómo se relacionan las partes del documento:
- Qué secciones dependen de otras
- Qué secciones se complementan
- Si hay secciones que se contradicen
- Si hay dependencias implícitas (sección 3 usa términos definidos en sección 1)

#### C3.3 Preguntas que responde el documento

Genera una lista de las preguntas que el documento aborda. Esto es el diferenciador principal: permite comprender el propósito y alcance del documento a partir de sus preguntas implícitas.

Ejemplo: "¿Quién es responsable de X?", "¿Cuáles son los pasos para Y?", "¿Qué restricciones aplican a Z?"

#### C3.4 Conclusiones y recomendaciones

Observaciones sobre la calidad estructural del documento:
- Secciones que podrían reordenarse
- Contenido que parece duplicado
- Bloques que no tienen relación con el resto
- Si el documento cumple con lo que su título sugiere
- Sugerencias de estructura (agregar sección de X, separar Y en dos partes)

De momento son solo observaciones. La modificación del documento queda para una segunda etapa.

---

### C4. Análisis a nivel de bloque

Disponible solo para documentos con estructura detectada (no para documentos narrativos/sin estructura):

- **Rol del bloque:** qué papel juega en su sección y en el documento completo.
- **Relaciones del bloque:** con qué otros bloques se complementa, depende, o contradice.

---

### C5. Configuración del LLM

El usuario puede:
- Seleccionar el LLM por defecto para los análisis
- Activar/desactivar auto-fallback (si un LLM falla, usar el otro automáticamente)
- Ver qué LLM se usó en cada análisis ejecutado

Si el auto-fallback está desactivado y un análisis falla, el sistema informa el error y ofrece reintentar o cambiar de LLM.

---

### C6. Persistencia y detección de cambios

- Todo análisis completado se guarda y no se re-ejecuta al volver.
- Si el documento cambia (detectable por fecha de modificación y tamaño), los análisis se marcan como "posiblemente desactualizado".
- El usuario decide si re-ejecutar análisis desactualizados.

---

### C7. Modelo de confianza (Trust by Evidence)

Se mantiene el principio de ADR-004:
- Cada afirmación del sistema incluye referencia al texto fuente (source_ref).
- El usuario puede verificar el origen de cada resultado.
- El sistema no promete precisión absoluta — promete trazabilidad.

---

### C8. Privacidad y procesamiento

Se mantienen los principios de ADR-005:
- Transparencia y consentimiento antes de procesar.
- Minimización: solo texto + prompts al LLM.
- Abstracción del proveedor.

---

## Fuera de alcance del MVP

- Análisis multi-documento y relaciones entre documentos
- Modificación/corrección del documento basada en análisis
- Sugerencias de texto actualizado
- Knowledge Graph completo
- Procesamiento local de IA
- Edición colaborativa
- Control de versiones documental
- DOCX, OCR, imágenes
- Confidence scores por resultado
- Detección de cambios por content hash (solo metadatos en MVP)

---

## Flujo principal del usuario

1. El usuario carga un documento.
2. El sistema informa sobre procesamiento externo y pide consentimiento (ADR-005).
3. El usuario da consentimiento.
4. El sistema ejecuta el **análisis base** (< 5 segundos).
5. Se muestra la **ficha del documento**: título, resumen, clasificación, estadísticas, estructura detectada.
6. El usuario ve un **panel de opciones** con los análisis disponibles según la clasificación.
7. El usuario selecciona un análisis (ej: "Construir índice").
8. El sistema ejecuta el análisis y muestra los resultados.
9. Los resultados se guardan. El usuario puede solicitar otros análisis.
10. Al volver al documento, todo lo previamente analizado está disponible sin re-ejecutar.

---

## Prioridad del MVP

### Must Have

- Cargar documento (formatos según ADR-003)
- Análisis base automático (resumen, clasificación, estadísticas, estructura)
- Ficha del documento visible en < 5 segundos
- Al menos 2 análisis bajo demanda funcionales (Construir índice + Preguntas que responde)
- Persistencia de resultados (no re-analizar)
- Source_ref en resultados (trazabilidad)
- Consentimiento de procesamiento externo
- Selector de LLM visible en la UI
- Indicador de estado de cada análisis

### Should Have

- Análisis "Relaciones entre secciones"
- Análisis "Conclusiones y recomendaciones"
- Análisis a nivel de bloque
- Auto-fallback de LLM configurable
- Detección de documento desactualizado (por metadatos)

### Could Have

- Consulta por lenguaje natural sobre el modelo guardado
- Exportar resultados del análisis

### Not Now

- Análisis multi-documento
- Sugerencias de modificación de texto
- Procesamiento local
- Comparación entre documentos
- Content hash para detección de cambios
- Colaboración

---

## Criterios de éxito

El MVP será exitoso si demuestra que:

- Un usuario puede comprender la estructura de un documento normativo sin leerlo completo.
- El análisis base se produce en menos de 5 segundos.
- Los análisis bajo demanda producen resultados útiles que el usuario no obtendría fácilmente leyendo.
- El "preguntas que responde" aporta comprensión diferenciada vs un simple resumen.
- Los resultados guardados permiten volver al documento sin repetir análisis.
- El usuario tiene control sobre qué se analiza y con qué LLM.
