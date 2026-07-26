# ADR-006 — Document Type Schemas and Analysis Configuration

> Estado: ***Superseded partially by ADR-007**
> Fecha: 2026-07-23
> Aprobada: 2026-07-23
> Depende de: ADR-001, ADR-002, ADR-003, ADR-004, ADR-005 (todas aprobadas)

---

# Contexto

Las ADRs anteriores definieron el alcance del MVP (mono-documento con análisis de calidad), el Knowledge Model (elementos tipados con relaciones opcionales), la ingesta (Markdown, TXT, PDF), el modelo de confianza (Trust by Evidence) y la privacidad (procesamiento externo con consentimiento).

Sin embargo, dos requisitos funcionales aprobados no pueden implementarse sin esta decisión:

**RF-06 — "El sistema debe identificar información faltante según la estructura esperada para el tipo de documento."**

Para que el sistema pueda determinar qué información falta, necesita saber qué se espera. Esto requiere definir qué tipos de documentos reconoce el MVP y cuál es la estructura esperada de cada uno.

**RF-04 — "El Knowledge Model puede incluir relaciones opcionales entre elementos cuando el sistema las identifica con suficiente confianza."**

Para que el sistema pueda extraer relaciones, necesita un vocabulario acotado de tipos de relaciones. Sin este vocabulario, los prompts no pueden instruir al LLM sobre qué buscar.

Adicionalmente, se necesita definir cómo se determina el tipo de un documento (¿lo elige el usuario?, ¿lo infiere el sistema?) y qué ocurre cuando un documento no encaja en ningún tipo conocido.

---

# Problema

¿Qué configuración de análisis necesita el MVP para evaluar la calidad de un documento y extraer relaciones entre sus elementos?

Específicamente:

1. ¿Qué tipos de documentos reconoce el MVP?
2. ¿Cuál es la estructura esperada (esquema) para cada tipo?
3. ¿Cómo se selecciona el tipo de documento?
4. ¿Qué vocabulario de relaciones se soporta?
5. ¿Para qué se usan las relaciones dentro del Knowledge Model?
6. ¿Qué ocurre si un documento no encaja en ningún tipo?
7. ¿Los esquemas y relaciones son fijos, configurables o extensibles en el MVP?

---

# Alternativas consideradas

---

## Alternativa 1 — Esquemas fijos embebidos con selección manual del tipo

**Descripción**

El MVP define un conjunto cerrado de tipos de documentos con sus esquemas embebidos en el código/configuración. El usuario selecciona manualmente el tipo de documento antes de iniciar el análisis. No hay inferencia automática. Los tipos de relaciones también son un vocabulario fijo.

Si el usuario no identifica su documento con ningún tipo, puede seleccionar un tipo "genérico" que realiza extracción sin evaluación de completitud.

Tipos de documentos propuestos:

| Tipo | Descripción | Elementos esperados |
|------|-------------|---------------------|
| PRD (Product Requirements Document) | Documento de requisitos de producto | propósito, usuarios/actores, requisitos funcionales, restricciones, criterios de éxito |
| Technical Spec | Especificación técnica | propósito, alcance, componentes/conceptos, interfaces, restricciones, decisiones |
| Policy / Process | Documento de política o proceso | propósito, alcance, actores/roles, reglas, procesos, excepciones |
| Generic | Cualquier documento | propósito (solo extracción, sin evaluación de completitud) |

Vocabulario de relaciones:

| Tipo de relación | Semántica | Ejemplo |
|------------------|-----------|---------|
| constrains | Un elemento restringe o limita a otro | regla → concepto |
| participates_in | Un actor participa en un proceso o contexto | actor → proceso |
| depends_on | Un elemento depende de otro para ser válido | requisito → concepto |
| contradicts | Un elemento contradice o conflictúa con otro | regla → regla |

Propósito de las relaciones:

- Habilitar la detección de inconsistencias (relaciones tipo `contradicts`).
- Facilitar la exploración del conocimiento (navegación entre elementos relacionados).
- Enriquecer las respuestas a consultas (evidencia de conexiones entre conceptos).
- Detectar elementos huérfanos (actores mencionados sin participación, reglas sin conceptos asociados).

**Ventajas**

- Implementación directa: los esquemas son datos estáticos conocidos en tiempo de desarrollo.
- El usuario tiene control explícito sobre cómo se evalúa su documento.
- Sin riesgo de clasificación incorrecta del tipo de documento.
- El vocabulario de relaciones cerrado permite prompts precisos y evaluación determinista.
- Los resultados de "información faltante" son predecibles y explicables.

**Desventajas**

- Requiere que el usuario sepa qué tipo de documento tiene (puede no ser obvio).
- Agrega un paso manual al flujo del usuario (seleccionar tipo antes de analizar).
- Los tipos definidos son limitados — documentos de otros dominios caen en "genérico" sin evaluación de completitud.
- La rigidez puede frustrar a usuarios cuyo documento es una mezcla de tipos.
- No escala sin intervención manual del desarrollador (agregar un tipo = cambiar código/config).

**MVP impact**

Bajo. Los esquemas se definen una vez y se embeben. La UI agrega un selector de tipo. No hay lógica de inferencia.

**Architectural impact**

Bajo. Los esquemas son constantes o archivos de configuración. El pipeline recibe el tipo como parámetro y aplica el esquema correspondiente.

**Future scalability**

Baja sin refactoring. Agregar tipos requiere intervención del desarrollador. No hay camino hacia personalización por usuario ni aprendizaje de nuevos tipos.

---

## Alternativa 2 — Esquemas fijos con inferencia automática del tipo

**Descripción**

Igual que la Alternativa 1 en cuanto a esquemas y vocabulario de relaciones, pero el tipo de documento se infiere automáticamente mediante el LLM como primer paso del análisis. El sistema clasifica el documento, aplica el esquema correspondiente y luego realiza la extracción y el análisis de calidad.

Si el LLM no puede clasificar con confianza, se aplica el tipo "genérico".

El flujo sería: ingesta → clasificación (tipo) → extracción (Knowledge Model) → calidad (según esquema del tipo).

**Ventajas**

- Sin fricción para el usuario: no necesita decidir ni conocer la taxonomía de tipos.
- Flujo más natural: "sube tu documento y el sistema se encarga".
- Permite que el sistema se beneficie del contenido del documento para elegir la evaluación más adecuada.

**Desventajas**

- La clasificación puede ser incorrecta, lo que produce evaluación de completitud errónea (se espera que un documento tenga "criterios de éxito" cuando no es un PRD).
- Introduce una llamada adicional al LLM (o un paso adicional en el prompt), aumentando latencia y costo.
- El usuario no sabe a priori contra qué esquema se evalúa su documento — menor transparencia.
- Si el LLM clasifica mal y el usuario no puede corregir, la experiencia es peor que sin clasificación.
- La clasificación automática puede generar alucinaciones de tipo (asignar un tipo con alta confianza incorrectamente).

**MVP impact**

Medio. Requiere diseñar y testear un paso de clasificación adicional. La calidad de la clasificación debe evaluarse antes del release.

**Architectural impact**

Medio. El pipeline se vuelve multi-step con dependencia entre steps (el tipo determina el esquema, el esquema determina la evaluación). Agrega un punto de fallo: si la clasificación falla, el análisis completo se degrada.

**Future scalability**

Media. La inferencia automática es el camino hacia la escalabilidad (no depender del usuario para cada tipo nuevo), pero sin mecanismo de corrección, los errores de clasificación se acumulan.

---

## Alternativa 3 — Esquemas fijos con selección híbrida (inferencia + confirmación del usuario)

**Descripción**

El sistema infiere automáticamente el tipo de documento como primer paso del análisis, pero presenta su sugerencia al usuario para confirmación antes de proceder con la evaluación de calidad. El usuario puede aceptar la sugerencia, cambiar el tipo, o seleccionar "genérico" si ninguno aplica.

Esquemas y vocabulario de relaciones son idénticos a las alternativas anteriores (fijos en MVP).

El flujo sería: ingesta → clasificación (sugerencia de tipo) → confirmación del usuario → extracción (Knowledge Model) → calidad (según esquema confirmado).

Tipos de documentos propuestos (mismos que Alternativa 1):

| Tipo | Descripción | Elementos esperados |
|------|-------------|---------------------|
| PRD | Documento de requisitos de producto | propósito, usuarios/actores, requisitos funcionales, restricciones, criterios de éxito |
| Technical Spec | Especificación técnica | propósito, alcance, componentes/conceptos, interfaces, restricciones, decisiones |
| Policy / Process | Documento de política o proceso | propósito, alcance, actores/roles, reglas, procesos, excepciones |
| Generic | Cualquier documento | propósito (solo extracción, sin evaluación de completitud) |

Vocabulario de relaciones propuesto (mismo que Alternativa 1):

| Tipo de relación | Semántica | Dirección | Ejemplo |
|------------------|-----------|-----------|---------|
| constrains | Un elemento restringe o limita a otro | dirigida | regla → concepto |
| participates_in | Un actor participa en un proceso o contexto | dirigida | actor → proceso |
| depends_on | Un elemento depende de otro para ser válido | dirigida | requisito → concepto |
| contradicts | Un elemento contradice o conflictúa con otro | bidireccional | regla ↔ regla |

Propósito arquitectónico de las relaciones:

- **Análisis de calidad:** Las relaciones tipo `contradicts` habilitan la detección de inconsistencias internas. Los elementos huérfanos (sin relaciones) pueden señalarse como potencialmente desconectados del contexto.
- **Navegación y exploración:** El usuario puede seguir relaciones para entender cómo se conectan los elementos del documento.
- **Consultas por lenguaje natural:** Las relaciones enriquecen las respuestas con contexto ("esta regla restringe el concepto X").
- **Verificación de consistencia:** Un actor referenciado en un proceso pero ausente de la lista de actores se detecta como inconsistencia vía la relación esperada pero faltante.

Fallback para documentos sin tipo:

- Si el sistema no puede inferir un tipo con confianza, sugiere "Generic".
- El tipo "Generic" soporta todas las capacidades centrales del MVP:
  - Generación completa del Knowledge Model (extracción de la taxonomía completa: propósito, conceptos, actores, reglas, procesos, restricciones).
  - Extracción de relaciones opcionales entre elementos.
  - Consultas por lenguaje natural sobre el Knowledge Model.
  - Análisis de consistencia interna (detección de contradicciones y ambigüedades entre elementos extraídos).
- La única capacidad intencionalmente deshabilitada para "Generic" es la **evaluación de completitud basada en esquema**, ya que no existe una estructura esperada contra la cual comparar.
- No se reporta "información faltante" para documentos genéricos porque no hay referencia definida. Las sugerencias se limitan a observaciones sobre la estructura observada.

**Ventajas**

- Combina la conveniencia de la inferencia automática con la transparencia del control del usuario.
- El usuario siempre sabe contra qué esquema se evalúa su documento (lo ve y lo confirma).
- Errores de clasificación se corrigen antes de que afecten el análisis.
- El paso de confirmación es ligero (un click para aceptar la sugerencia).
- Genera datos sobre la calidad de la inferencia (¿con qué frecuencia el usuario corrige?) para mejorar en el futuro.
- El tipo "Generic" como fallback garantiza que cualquier documento puede analizarse (aunque con resultados de calidad reducidos).

**Desventajas**

- Agrega un paso al flujo del usuario (confirmación del tipo), aunque sea ligero.
- Si la inferencia es mala consistentemente, el usuario pierde confianza en el sistema ("siempre tengo que corregirlo").
- Requiere tanto la lógica de inferencia como la UI de selección (ambos componentes).
- El flujo tiene tres pasos antes del análisis: consentimiento (ADR-005) + carga + confirmación de tipo. Puede percibirse como lento.

**MVP impact**

Medio. Requiere: lógica de inferencia de tipo (prompt), UI de selección/confirmación, definición de esquemas, y el paso de clasificación en el pipeline. Más complejo que selección manual, pero con mejor UX a largo plazo.

**Architectural impact**

Medio. El pipeline es multi-step (clasificación → confirmación → extracción → calidad). El tipo confirmado por el usuario se convierte en un parámetro que determina el esquema aplicado. La separación es limpia y el pipeline permanece modular.

**Future scalability**

Alta. La combinación de inferencia + confirmación + datos de corrección es el camino natural hacia: tipos aprendidos, tipos personalizados, y mejora de la clasificación. Agregar un nuevo tipo es agregar un esquema a la configuración y actualizar el prompt de clasificación.

---

# Sobre la extensibilidad de esquemas y relaciones en el MVP

Independientemente de la alternativa elegida:

- **Los esquemas seleccionados representan las capacidades iniciales de análisis del MVP**, no una taxonomía exhaustiva de todos los tipos de documentos posibles. Se eligieron porque cubren los casos de uso más relevantes para los usuarios objetivo (requisitos de producto, especificaciones técnicas, documentos de proceso). Esquemas adicionales pueden incorporarse en versiones futuras sin modificar la arquitectura de análisis subyacente.
- **En el MVP los esquemas son fijos.** Se definen durante el desarrollo y no se modifican en runtime.
- **El vocabulario de relaciones es fijo.** Los 4 tipos propuestos son los únicos que el LLM busca.
- **La estructura permite extensión futura** porque los tipos se representan como strings (no enums cerrados ni columnas), lo que permite agregar nuevos tipos sin romper el esquema del Knowledge Model.
- **La configuración dinámica de taxonomías y tipos personalizados queda explícitamente fuera del MVP** (documentado en Not Now desde ADR-001).

---

# Recomendación

**Alternativa 3 — Esquemas fijos con selección híbrida (inferencia + confirmación del usuario).**

**Razonamiento:**

1. **Transparencia alineada con el modelo de confianza (ADR-004).** El MVP se basa en Trust by Evidence: el usuario puede verificar todo. Si el sistema decide silenciosamente contra qué esquema evalúa (Alternativa 2), rompe ese principio. Si el usuario debe saber siempre qué tipo se aplica, la confirmación es el mecanismo natural.

2. **UX balanceada.** La selección puramente manual (Alternativa 1) requiere que el usuario conozca la taxonomía. La inferencia pura (Alternativa 2) no da control. El híbrido ofrece lo mejor de ambos: conveniencia + transparencia.

3. **El paso de confirmación es mínimo.** Si la inferencia es buena (y para documentos típicos como PRDs o specs lo será), el usuario solo hace un click. Si es mala, puede corregir sin penalización.

4. **Genera datos de calidad.** Cada corrección del usuario es una señal para mejorar la clasificación en futuras iteraciones. Esto es coherente con el feedback pasivo aprobado en ADR-004 (Should Have).

5. **El fallback "Generic" garantiza que el sistema siempre funciona.** Un documento que no encaja en ningún tipo sigue obteniendo valor (extracción + inconsistencias internas), solo pierde la evaluación de completitud. Esto es honesto: sin referencia, no se puede afirmar que algo falta.

6. **El vocabulario de 4 relaciones es deliberadamente acotado.** Un vocabulario reducido:
   - Mantiene el Knowledge Model simple y comprensible para el usuario.
   - Mejora la consistencia de la extracción: el LLM busca exactamente 4 tipos bien definidos en lugar de intentar categorizar relaciones ambiguas.
   - Reduce el ruido: menos tipos de relaciones significa menos relaciones incorrectas o ambiguas generadas.
   - Simplifica el diseño de prompts: instrucciones precisas y evaluables sobre qué buscar.
   - Proporciona suficiente expresividad semántica para los usos del MVP (inconsistencias, navegación, restricciones, dependencias) sin complejidad innecesaria.

---

# Decisiones resueltas por esta ADR

| # | Decisión | Resolución |
|---|----------|------------|
| 1 | Tipos de documentos del MVP | PRD, Technical Spec, Policy/Process, Generic |
| 2 | Esquema esperado por tipo | Tabla de elementos esperados por tipo (definida arriba) |
| 3 | Selección del tipo | Híbrida: inferencia automática + confirmación del usuario |
| 4 | Vocabulario de relaciones | 4 tipos: constrains, participates_in, depends_on, contradicts |
| 5 | Propósito de las relaciones | Calidad, navegación, consultas, consistencia |
| 6 | Fallback para documentos sin tipo | Tipo "Generic": extracción completa sin evaluación de completitud |
| 7 | Extensibilidad en MVP | Esquemas y relaciones fijos; estructura permite extensión futura |

---

# Decisiones diferidas a diseño técnico

| Decisión | Justificación |
|----------|---------------|
| Formato de almacenamiento de esquemas (archivos de configuración, constantes en código, o tabla) | Detalle de implementación sin impacto arquitectónico |
| Prompt exacto para inferencia de tipo | Depende del modelo elegido; se itera durante implementación |
| Si la inferencia de tipo y la extracción ocurren en una o dos llamadas al LLM | Optimización de latencia/costo; testeable durante desarrollo |
| Diseño visual del selector de tipo y la confirmación | Decisión de UX |
| Lógica exacta de matching para detectar relaciones | Prompt engineering; se refina con pruebas |
| Umbral de confianza para sugerir un tipo vs. defaultear a "Generic" | Se calibra con datos reales durante desarrollo |
| Presentación visual de "información faltante" vs. "documento genérico sin evaluación" | Diseño de UX |

---

# Decisiones intencionalmente fuera del alcance (futuras iteraciones)

| Decisión | Justificación |
|----------|---------------|
| Tipos de documentos personalizados por el usuario | Requiere configuración dinámica de taxonomías (Not Now) |
| Aprendizaje de nuevos tipos a partir de uso | Requiere fine-tuning o mejora automática (Not Now) |
| Tipos de relaciones inter-documento | Requiere multi-documento (Not Now) |
| Esquemas específicos de dominio (legal, médico, financiero) | Fuera del alcance del MVP; requiere validación con usuarios de esos dominios |
| Herencia o composición de tipos (un documento que es "PRD + Technical Spec") | Complejidad prematura para el MVP |
| Vocabulario de relaciones extensible por el usuario | Requiere configuración dinámica (Not Now) |

---

# Decisión final

**Decisión aprobada: Alternativa 3 — Esquemas fijos con selección híbrida (inferencia + confirmación del usuario).**

Una vez aplicada, los documentos afectados deben actualizarse:

- `.specs/001-foundation/spec.md` — definir tipos de documentos soportados, esquemas esperados, vocabulario de relaciones, mecanismo de selección de tipo, y comportamiento del tipo "Generic" como parte de RF-04 y RF-06.
- `docs/product/03-prd.md` — agregar el paso de selección/confirmación de tipo al flujo del usuario, documentar los tipos soportados en una nueva subsección, y explicar el comportamiento diferenciado entre documentos tipados y genéricos.
