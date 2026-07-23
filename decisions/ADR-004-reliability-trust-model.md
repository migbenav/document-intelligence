# ADR-004 — Reliability and Analysis Trust Model

> Estado: **Approved**
> Fecha: 2026-07-23
> Aprobada: 2026-07-23
> Depende de: ADR-001-mvp-scope.md, ADR-002-knowledge-model.md, ADR-003-document-ingestion.md

---

# Contexto

Las tres ADRs anteriores definieron qué hace el MVP (análisis de calidad documental sobre un documento), cómo representa el conocimiento (Knowledge Model con elementos tipados y relaciones opcionales) y qué entra al sistema (Markdown, TXT, PDF). Lo que no se ha definido es cómo el usuario confía en los resultados.

El sistema depende de un LLM para generar el Knowledge Model y el análisis de calidad. Los LLMs son no-deterministas y pueden producir resultados incorrectos (alucinaciones). Sin un modelo de confianza, el usuario no puede distinguir un resultado correcto de uno inventado.

Tres observaciones de la revisión arquitectónica señalan este problema:

**OBS-13 — No hay mecanismo para manejar alucinaciones ni feedback del usuario**

El spec no describe cómo se gestionan los errores del LLM ni cómo el usuario puede corregir o validar los resultados. Sin mecanismo de verificación o corrección, el usuario no tiene forma de confiar en los resultados. Esto mina directamente el criterio de validación de la hipótesis.

**OBS-07 — "Análisis reproducible" contradice la naturaleza no-determinista de los LLM**

El RNF indica "el análisis debe ser reproducible", pero los LLMs generan resultados diferentes ante el mismo input dependiendo de temperatura, versión del modelo y otros factores. Sin acotar qué significa "reproducible" en este contexto, el requisito es imposible de cumplir y no se puede validar.

**OBS-15 — No se define si las respuestas deben incluir citaciones al texto fuente**

Si el usuario no puede verificar de dónde proviene un elemento del Knowledge Model o una respuesta a una pregunta, no tiene forma de evaluar su corrección. La citación es el mecanismo más directo para que el usuario verifique sin necesidad de releer el documento completo.

---

# Problema

¿Cómo debe el MVP garantizar que el usuario pueda confiar en los resultados del análisis y cómo se gestiona la naturaleza no-determinista del LLM?

Específicamente:

1. ¿Cómo se acota "reproducibilidad" con un modelo no-determinista?
2. ¿Cómo puede el usuario verificar que un resultado es correcto?
3. ¿Cómo se manejan las alucinaciones del LLM?
4. ¿Puede el usuario corregir o dar feedback sobre los resultados?
5. ¿Las respuestas y elementos del Knowledge Model deben incluir citaciones al texto fuente?

---

# Alternativas consideradas

---

## Alternativa 1 — Trust by Evidence (citaciones + reproducibilidad acotada)

**Descripción**

El sistema incluye referencias al texto fuente (evidence references) en cada elemento del Knowledge Model y en cada respuesta. El usuario confía en los resultados porque puede trazar el origen de cada afirmación hasta el documento original.

El enfoque se centra en la trazabilidad de evidencia en lugar de intentar garantizar que el LLM sea correcto el 100% del tiempo. El sistema no promete perfección; promete que todo lo que afirma puede verificarse.

La reproducibilidad se acota a consistencia estructural: dado el mismo documento y la misma configuración, el sistema produce los mismos hallazgos principales, no texto idéntico.

Componentes:

- Cada elemento del Knowledge Model incluye un campo `source_ref` con referencia flexible al texto fuente.
- Las respuestas a consultas incluyen evidencia trazable al documento original.
- El sistema usa parámetros de generación controlados (temperatura mínima cuando esté disponible), tracking de versión del modelo, y prompts versionados para maximizar consistencia.
- Prompts versionados e inmutables por release.

**Ventajas**

- Mecanismo de confianza simple y efectivo: el usuario puede verificar sin que el sistema necesite ser "correcto" el 100% del tiempo.
- No requiere infraestructura de feedback ni almacenamiento de correcciones.
- Las citaciones ya están contempladas en la estructura del Knowledge Model (ADR-002 incluye `source_ref`).
- La definición de reproducibilidad es realista y testeable.
- Implementación directa: el LLM ya puede generar referencias si el prompt lo solicita.

**Desventajas**

- No hay forma de mejorar los resultados basándose en uso real (sin feedback loop).
- Si el LLM alucina una referencia (apunta a un fragmento que no dice lo que el sistema afirma), la confianza del usuario se rompe.
- La responsabilidad de la validación recae completamente en el usuario.
- No se aprende de los errores — cada análisis parte de cero.

**Impacto en MVP scope**

Bajo. Las referencias son una extensión natural del Knowledge Model que ya se definió. La reproducibilidad se resuelve con constraints de configuración, no con código adicional.

**Impacto en arquitectura**

Bajo. Requiere que los prompts soliciten referencias, que el parser del output las capture, y que `source_ref` se valide contra el documento original (verificación de que la evidencia existe realmente en el texto).

**Escalabilidad futura**

Media. Las referencias son una base sobre la cual construir feedback ("esta referencia es incorrecta") y evaluación automatizada. Pero sin feedback, no hay datos para mejorar.

---

## Alternativa 2 — Trust by Evidence + confidence scores + feedback pasivo

**Descripción**

Extiende la Alternativa 1 con dos capacidades adicionales:

1. **Confidence scores:** Cada elemento del Knowledge Model incluye un nivel de confianza (alto, medio, bajo) que indica cuánta certeza tiene el sistema en esa extracción. Los elementos con confianza baja se señalan visualmente al usuario.

2. **Feedback pasivo:** El usuario puede marcar un elemento como "incorrecto" o "irrelevante". Esta información se almacena asociada al análisis pero no se usa para re-procesar en tiempo real. Sirve como dato para mejorar prompts en futuras iteraciones.

Componentes:

- Referencias al texto fuente (como Alternativa 1).
- Campo `confidence: high | medium | low` en cada elemento.
- Botón/acción para marcar un elemento como incorrecto (sin edición del contenido).
- Almacenamiento del feedback junto al Knowledge Model.
- Reproducibilidad acotada igual que Alternativa 1.

**Ventajas**

- El usuario tiene más información para decidir qué resultados revisar con más cuidado (los de baja confianza).
- El feedback pasivo genera datos para mejorar prompts sin complejidad de re-procesamiento.
- Transparencia: el sistema reconoce sus limitaciones señalando confianza baja.
- Mejor experiencia de usuario: no todo se presenta con la misma certeza.

**Desventajas**

- Los confidence scores generados por un LLM no son confiables per se — un modelo puede asignar "alta confianza" a una alucinación.
- Requiere calibrar qué significa "alto", "medio" y "bajo" — sin datos históricos, la calibración es arbitraria.
- El feedback pasivo no tiene efecto inmediato para el usuario, lo que puede percibirse como un "buzón de quejas" sin respuesta.
- Mayor complejidad de UI (indicadores de confianza, botones de feedback).
- La métrica de confianza puede generar falsa seguridad si no está bien calibrada.

**Impacto en MVP scope**

Medio. Los confidence scores requieren diseño de prompts específicos y un esquema de UI para mostrarlos. El feedback pasivo requiere un modelo de almacenamiento extendido y una interacción de usuario adicional.

**Impacto en arquitectura**

Medio. El Knowledge Model necesita un campo adicional por elemento. Se necesita una capa de persistencia para feedback. La UI necesita componentes de interacción (marcar como incorrecto).

**Escalabilidad futura**

Alta. Los confidence scores y el feedback son los datos necesarios para implementar mejora continua de prompts, fine-tuning, y evaluación automatizada en iteraciones futuras.

---

## Alternativa 3 — Trust by Evidence + validation layer + user correction

**Descripción**

Además de las referencias, el sistema incluye una capa de validación automatizada que verifica la consistencia interna del Knowledge Model antes de presentar resultados. El usuario puede corregir elementos directamente (editar, eliminar, reagrupar).

Componentes:

- Referencias al texto fuente.
- Capa de validación post-análisis:
  - Verifica que las referencias existen realmente en el documento.
  - Detecta duplicados en el Knowledge Model.
  - Verifica coherencia entre elementos (un actor referenciado en una regla existe en la lista de actores).
- Edición directa del Knowledge Model por el usuario (corregir texto, cambiar tipo, eliminar elemento, agregar relación).
- Las correcciones se persisten como "override" del usuario sobre el análisis automático.
- Reproducibilidad: el análisis base es regenerable; las correcciones del usuario se aplican como capa superior.

**Ventajas**

- Máxima confianza: el sistema se auto-valida y el usuario puede corregir lo que esté mal.
- La validación automática de referencias atrapa alucinaciones antes de que el usuario las vea.
- El usuario tiene control total sobre el resultado final.
- Genera el dataset más rico para mejora futura (correcciones explícitas).

**Desventajas**

- Complejidad significativa para un MVP: edición de grafos, persistencia de overrides, merge de correcciones con re-análisis.
- La capa de validación requiere un segundo pass de procesamiento (aumento de latencia y costo).
- Riesgo de convertir el MVP en un editor de Knowledge Models en lugar de un analizador automático.
- La edición directa puede confundir la propuesta de valor: "¿el sistema me ayuda o tengo que corregirlo todo yo?"
- Scope creep potencial si la edición se vuelve compleja.

**Impacto en MVP scope**

Alto. La validación automatizada, la edición de elementos y la persistencia de correcciones son funcionalidades completas que agregan semanas de desarrollo.

**Impacto en arquitectura**

Alto. Requiere una capa de validación como servicio separado, un modelo de datos que soporte overrides del usuario sobre el análisis base, y una UI de edición de elementos estructurados.

**Escalabilidad futura**

Muy alta. Las correcciones del usuario son gold-standard data para evaluación y mejora. La capa de validación es reutilizable para multi-documento. Pero la complejidad inicial puede retrasar la entrega del MVP.

---

# Decisión final

## Decisión aprobada: Alternativa 1 — Trust by Evidence (citations + bounded reproducibility)

El MVP se centra en la trazabilidad de evidencia como mecanismo de confianza. No intenta garantizar que el LLM sea correcto, sino que todo resultado pueda ser verificado por el usuario trazándolo hasta el documento original.

---

## Reproducibilidad acotada

El sistema usa parámetros de generación controlados (temperatura mínima cuando esté disponible), tracking fijo de versión del modelo, y prompts versionados para maximizar consistencia.

**Reproducibilidad** en el contexto de Document Intelligence significa que, dado:

- el mismo documento,
- la misma configuración del modelo (versión trackeada),
- la misma versión de prompts,

el sistema produce:

- los mismos elementos principales de conocimiento (propósito, conceptos clave, actores principales);
- los mismos hallazgos críticos (inconsistencias, información faltante);
- un Knowledge Model estructuralmente comparable.

**No se garantiza output textual idéntico.** Se garantiza consistencia en estructura y hallazgos principales.

Esta definición es testeable mediante evaluación automatizada (comparar estructura de dos runs del mismo documento).

---

## Source references (source_ref)

Cada elemento del Knowledge Model incluye un campo `source_ref` definido como una **referencia de evidencia flexible** que contiene la información disponible para trazar el elemento hasta el documento original.

`source_ref` puede incluir (según disponibilidad por formato):

- **document_id:** identificador del documento analizado.
- **page:** número de página (cuando esté disponible, principalmente PDF).
- **section:** sección o capítulo (cuando esté disponible, principalmente Markdown headings).
- **chunk_id:** identificador del fragmento de texto procesado.
- **evidence:** texto span o extracto textual del documento fuente que respalda el elemento.

No se asume un formato de referencia basado en líneas porque los PDFs no contienen líneas estables. La referencia se adapta al formato del documento de origen.

**El objetivo es que todo elemento generado pueda ser trazado hasta el documento original.**

Las respuestas a consultas por lenguaje natural también incluyen evidencia trazable.

---

## Verificación de referencias

Como parte del pipeline de generación, el sistema verifica que la evidencia referenciada (`evidence` text span) existe realmente en el documento original. Si una referencia no puede ser verificada, el elemento se marca como no-verificado.

---

## Feedback del usuario (Should Have)

El usuario puede marcar un elemento del Knowledge Model como:

- **incorrecto** — el contenido no refleja lo que dice el documento.
- **irrelevante** — el elemento no aporta valor al análisis.

El feedback se almacena asociado al análisis.

**El feedback NO incluye:**

- Edición directa del Knowledge Model.
- Flujos de corrección manual.
- Re-entrenamiento ni mejora automática basada en feedback.
- Loops de re-procesamiento.

Estas capacidades quedan para iteraciones futuras.

---

## Non-goals del MVP

El MVP **no intenta** proporcionar:

- Garantía de precisión del 100% del LLM.
- Validación automatizada completa de todo el razonamiento.
- Capacidades de edición del Knowledge Model.
- Fine-tuning basado en feedback del usuario.
- Framework de evaluación completo.

El MVP se centra en demostrar que la trazabilidad de evidencia es suficiente para que el usuario confíe en el análisis y evalúe si le aporta valor.

---

## Prioridad

| Capacidad | Prioridad MVP |
|-----------|---------------|
| Source references (source_ref) en cada elemento | Must Have |
| Verificación de que la evidencia existe en el documento | Must Have |
| Definición de reproducibilidad acotada (consistencia estructural) | Must Have |
| Parámetros de generación controlados + prompts versionados | Must Have |
| Evidencia trazable en respuestas a consultas | Must Have |
| Feedback pasivo (marcar como incorrecto/irrelevante) | Should Have |
| Confidence scores | Not now |
| Edición directa del Knowledge Model | Not now |
| Capa de validación completa | Not now |
| Fine-tuning basado en feedback | Not now |

---

## Documentos afectados

Una vez aprobada, los siguientes documentos deben actualizarse:

- `.specs/001-foundation/spec.md` — actualizar RNF de reproducibilidad con la definición acotada; agregar requisitos de source_ref y verificación de evidencia; agregar feedback pasivo como Should Have; documentar non-goals.
- `docs/product/03-prd.md` — actualizar capacidades y criterios de éxito con el modelo de confianza basado en evidencia.
