# ADR-001 — Alcance del MVP

> Estado: **Aprobada**
> Fecha: 2026-07-23
> Aprobada: 2026-07-23
> Autores: Revisión arquitectónica inicial

---

# Contexto

Durante la revisión de la documentación del proyecto se identificaron tres inconsistencias que afectan directamente la definición del alcance del MVP:

**OBS-01 — Contradicción en la prioridad de detección de inconsistencias**

La Product Vision describe la detección de inconsistencias y contradicciones como parte central del MVP. Sin embargo, el PRD la clasifica como "Should Have", lo que la deja fuera de la entrega obligatoria. Dado que la detección de inconsistencias es el principal diferenciador del producto frente a herramientas de IA generativas, esta contradicción impide tomar decisiones de diseño con claridad.

**OBS-02 — Conflicto entre visión multi-documento y MVP mono-documento**

La Product Vision menciona explícitamente "mantener relaciones entre documentos" y "detectar inconsistencias entre documentos relacionados" como capacidades objetivo. La spec, en cambio, restringe el MVP a un único documento. Este conflicto no está documentado como una decisión tomada, sino que aparece como una inconsistencia no resuelta. Tiene consecuencias arquitectónicas significativas: analizar relaciones entre documentos requiere un modelo de datos, un motor de correlación y una UX distintos a los de un análisis mono-documento.

**OBS-08 — "Detectar elementos faltantes" sin referencia definida**

El PRD incluye como capacidad C4 la detección de "elementos faltantes". Sin embargo, para que un sistema pueda determinar que algo falta, necesita una referencia contra la cual comparar: una plantilla, un esquema esperado o un corpus de documentos relacionados. Analizando un único documento de forma aislada, esta capacidad no es implementable de forma determinista.

**Pregunta que resuelve este ADR:**

¿Qué capacidades debe incluir el MVP para validar la hipótesis central del producto con el menor alcance técnico posible?

**Hipótesis central a validar (definida en Problem Discovery):**

> Si representamos el conocimiento contenido en un documento mediante un modelo estructurado y utilizamos IA para analizarlo, los usuarios podrán comprender documentos complejos más rápidamente, detectar inconsistencias antes de que generen problemas, y mantener documentación más consistente y reutilizable.

---

# Decisión a tomar

Determinar qué alcance debe tener el MVP en dos dimensiones:

1. **Número de documentos:** ¿trabaja el MVP con un único documento o con un corpus de documentos relacionados?
2. **Capacidades incluidas:** ¿qué funcionalidades son estrictamente necesarias para validar la hipótesis y demostrar el diferenciador del producto?

---

# Alternativas consideradas

---

## Alternativa 1 — MVP mono-documento sin detección de inconsistencias

**Descripción**

El MVP se limita a analizar un único documento de forma aislada. Las capacidades incluidas son: ingesta de documento, extracción de conocimiento básico (propósito, conceptos, actores, reglas, restricciones) y consulta mediante lenguaje natural. La detección de inconsistencias y relaciones entre documentos se pospone completamente.

**Ventajas**

- Alcance técnico mínimo: el sistema no necesita persistencia entre documentos ni modelo de correlación.
- Menor tiempo de desarrollo y menor complejidad inicial.
- Permite validar el pipeline de extracción de conocimiento de forma aislada.

**Desventajas**

- No demuestra el diferenciador del producto frente a un chatbot genérico sobre documentos.
- La hipótesis central incluye "detectar inconsistencias antes de que generen problemas", que queda sin validar.
- El usuario no puede apreciar el valor de la representación estructurada si no se usa para detectar ningún problema real.

**Impacto técnico**

Bajo. Sistema stateless por sesión. No requiere modelo de datos persistente entre documentos ni lógica de comparación.

**Impacto en validación del producto**

Bajo. Un MVP que solo responde preguntas sobre un documento es funcionalmente equivalente a herramientas ya existentes. No demuestra la hipótesis central.

---

## Alternativa 2 — MVP mono-documento con análisis de calidad documental

**Descripción**

El MVP analiza un único documento y produce un análisis de calidad documental basado en su representación de conocimiento estructurado. Las capacidades incluidas son:

- Extracción de conocimiento (propósito, conceptos, actores, reglas, restricciones).
- Detección de inconsistencias internas (contradicciones dentro del mismo documento).
- Identificación de información faltante según la estructura esperada para el tipo de documento.
- Sugerencias de mejora basadas en el conocimiento extraído.
- Consulta mediante lenguaje natural sobre el conocimiento extraído.

El análisis multi-documento y las relaciones entre documentos quedan fuera del MVP.

**Ventajas**

- Demuestra el diferenciador del producto: el sistema no solo extrae conocimiento sino que razona sobre su calidad y consistencia interna.
- Alcance controlado: trabajar con un solo documento mantiene la complejidad técnica manejable.
- Valida la hipótesis central de forma parcial pero significativa.
- Resuelve OBS-08: "información faltante" se acota a una estructura esperada por tipo de documento, sin necesitar comparación entre documentos.
- La arquitectura resultante es extensible hacia análisis multi-documento en iteraciones posteriores.

**Desventajas**

- Requiere definir una taxonomía de tipos de documentos y sus estructuras esperadas antes del diseño.
- La detección de inconsistencias intra-documento es menos impactante que la inter-documento, que es el caso de uso más potente descrito en el Problem Discovery.
- Puede generar la percepción de que el producto "solo analiza un documento a la vez".

**Impacto técnico**

Medio. Requiere un modelo de conocimiento persistente por sesión, lógica de detección de contradicciones sobre la estructura extraída, y un esquema de referencia configurable por tipo de documento.

**Impacto en validación del producto**

Medio-alto. Demuestra que la representación estructurada habilita capacidades que el texto plano no permite. Valida la hipótesis de forma parcial y suficiente para un MVP.

---

## Alternativa 3 — MVP multi-documento con relaciones y detección de inconsistencias inter-documento

**Descripción**

El MVP permite cargar un conjunto de documentos relacionados. El sistema construye un modelo de conocimiento unificado, detecta relaciones entre documentos y señala inconsistencias o contradicciones entre ellos. Replica fielmente la visión completa del producto desde la primera entrega.

**Ventajas**

- Valida la hipótesis central en su totalidad.
- Demuestra el diferenciador más potente del producto: la inteligencia sobre corpus documentales.
- Alinea MVP con Product Vision sin necesidad de reconciliar documentos.

**Desventajas**

- Alcance técnico significativamente mayor: requiere modelo de datos relacional entre documentos, lógica de correlación cruzada, y una UX que gestione colecciones.
- Mayor riesgo de no terminar en el tiempo previsto para un MVP.
- Sin validar primero el análisis de un documento, se construye sobre una base no probada.
- El feedback del primer usuario se obtiene más tarde.

**Impacto técnico**

Alto. Requiere modelo de datos persistente, identificación de entidades compartidas entre documentos, lógica de inferencia de relaciones y detección de contradicciones cruzadas. Complejidad de órdenes de magnitud superior a la Alternativa 1.

**Impacto en validación del producto**

Alto. Valida completamente la hipótesis, pero a costa de un MVP más pesado que retrasa la obtención de aprendizaje temprano.

---

# Recomendación

**Alternativa 2 — MVP mono-documento con análisis de calidad documental.**

**Razonamiento:**

La hipótesis central del producto no es solo "extraer conocimiento de un documento" — eso ya lo hacen herramientas existentes. El diferenciador es usar esa representación estructurada para razonar sobre el conocimiento y detectar problemas que el texto plano no permite ver.

La Alternativa 1 no demuestra ese diferenciador. La Alternativa 3 lo demuestra completamente pero introduce un riesgo de alcance incompatible con un MVP.

La Alternativa 2 equilibra ambos objetivos: valida la hipótesis central con un alcance técnico manejable, y deja la arquitectura preparada para escalar a multi-documento en la siguiente iteración.

Para que esta alternativa sea viable, es necesario resolver previamente:

- OBS-03: definir la estructura del modelo de conocimiento.
- OBS-14: decidir si la taxonomía es fija o extensible por tipo de documento.
- OBS-07: acotar qué significa "análisis reproducible" con un LLM.

---

# Decisión final

**Decisión aprobada: Alternativa 2 — MVP mono-documento con análisis de calidad documental.**

## Alcance acordado del MVP

El MVP incluirá las siguientes capacidades sobre un único documento:

1. **Extracción de conocimiento estructurado** — propósito, conceptos, actores, reglas, restricciones y procesos.
2. **Detección de inconsistencias internas** — contradicciones y ambigüedades dentro del mismo documento.
3. **Identificación de información faltante** — según la estructura esperada para el tipo de documento analizado.
4. **Sugerencias de mejora** — basadas en el conocimiento extraído y las brechas identificadas.
5. **Consulta por lenguaje natural** — sobre el conocimiento generado durante el análisis.

## Fuera del alcance del MVP

- Análisis multi-documento.
- Detección de inconsistencias entre documentos relacionados.
- Relaciones cruzadas entre documentos.
- Colaboración y edición.
- Control de versiones documental.
- Integraciones externas.

## Implicaciones para la especificación

Los documentos afectados deben actualizarse para reflejar esta decisión:

- `docs/product/03-prd.md` — reconciliar priorización MoSCoW y capacidades con el alcance acordado.
- `docs/product/01-product-vision.md` — distinguir explícitamente qué es MVP y qué es visión a futuro.
- `.specs/001-foundation/spec.md` — actualizar alcance, historias de usuario, requisitos funcionales y criterios de aceptación.
