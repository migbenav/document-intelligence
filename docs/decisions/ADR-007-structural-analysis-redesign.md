# ADR-007 — Rediseño del modelo de análisis: de extracción de entidades a comprensión estructural progresiva

> Estado: **Approved**
> Fecha: 2026-07-26
> Aprobada: 2026-07-26
> Depende de: ADR-001, ADR-003, ADR-004, ADR-005 (vigentes sin cambios)
> Supersedes parcialmente: ADR-002, ADR-006
> Motivada por: Retrospectiva 001 (docs/retrospectives/001-knowledge-model-disconnect.md)

---

## Contexto

Tras implementar las Features 1-5 del MVP, se identificó una desconexión fundamental entre la intención del producto y lo que se construyó. La retrospectiva 001 documenta el análisis completo.

**Problema central:** La ADR-002 definió el Knowledge Model como una "lista de elementos tipados con relaciones opcionales" (6 tipos fijos: propósito, conceptos, actores, reglas, procesos, restricciones). Esta definición convirtió la comprensión documental en extracción de entidades — un pipeline que produce una lista larga de "cosas encontradas" sin preservar la estructura del documento ni ofrecer comprensión progresiva.

**Resultado:** Un sistema lento (30-90s), que no ayuda a entender documentos rápidamente, no preserva la estructura documental, no ofrece opciones al usuario, y no prepara el terreno para la comparación multi-documento futura.

**Intención original del producto:** Una herramienta que ayude a comprender la estructura de documentos (reglamentos, políticas, manuales) rápidamente, preservando su organización, permitiendo análisis progresivo bajo demanda, y guardando ese conocimiento estructural para eventualmente detectar dependencias y contradicciones entre documentos.

---

## Problema

¿Cómo debe el sistema analizar un documento para que el usuario lo comprenda sin leerlo, con una primera salida rápida y opciones de profundización bajo demanda?

Específicamente:

1. ¿Qué debe producir el análisis inicial (automático, rápido)?
2. ¿Qué análisis profundos están disponibles bajo demanda?
3. ¿Cómo se preserva la estructura del documento?
4. ¿Cómo se persisten los resultados para no re-analizar?
5. ¿Cómo se adapta el sistema según el tipo de documento?
6. ¿Cómo interactúa el usuario con las opciones de análisis?
7. ¿Cómo se gestiona la selección del LLM y los fallos?

---

## Decisión

### Principio rector

El objetivo del sistema no es extraer entidades de un documento. Es **ayudar al usuario a comprender el documento sin leerlo** y guardar ese entendimiento para uso futuro.

---

### 1. Análisis en dos niveles

El análisis se divide en dos niveles claramente diferenciados:

#### Nivel 1 — Análisis base (automático, rápido, < 5 segundos)

Se ejecuta automáticamente al cargar el documento. Combina procesamiento local (sin LLM) con una llamada LLM corta y ligera.

**Sin LLM (instantáneo):**
- Título del documento (del filename o primer heading)
- Estadísticas: número de páginas/bloques/párrafos, secciones detectadas
- Tipo de organización detectada (artículos numerados, secciones con heading, libre)
- Niveles de jerarquía
- Presencia de índice existente
- Metadatos: fecha de última modificación, tamaño del archivo

**Con LLM (una llamada corta, modelo ligero):**
- Resumen de 2-3 líneas: de qué trata el documento, cuál es su objetivo
- Clasificación del documento (normativo, guía, manual, procedimiento, artículo, reporte, otro)

**Resultado:** Una "ficha" del documento que se muestra inmediatamente y se guarda en DB.

#### Nivel 2 — Análisis bajo demanda (el usuario elige qué ejecutar)

El usuario ve la ficha del Nivel 1 y decide qué análisis profundos solicitar. Cada análisis se ejecuta por separado y su resultado se guarda como capa acumulativa en el modelo del documento.

**Opciones a nivel de documento:**
- **Construir/revisar índice** — genera la estructura del documento como árbol de secciones con roles funcionales. Si ya tiene índice, valida que refleje el contenido real.
- **Relaciones entre secciones** — identifica dependencias, complementos y contradicciones entre las partes del documento.
- **Preguntas que responde** — lista las preguntas que el documento aborda (diferenciador clave).
- **Conclusiones y recomendaciones** — observaciones sobre la calidad estructural: secciones que podrían reordenarse, bloques que faltan, contenido duplicado.

**Opciones a nivel de bloque (disponibles solo para documentos con estructura detectada):**
- **Rol del bloque** — qué papel juega en su sección y en el documento (define, clasifica, establece, recomienda, lista, restringe).
- **Relaciones del bloque** — con qué otros bloques se complementa, se relaciona, se contradice.

---

### 2. Modelo de estructura documental

El análisis preserva la estructura del documento como un **árbol jerárquico de bloques** con relaciones entre bloques que no son padre-hijo.

```
DocumentStructure:
  document_id: string
  title: string
  summary: string # 2-3 líneas
  classification: string # normativo, guía, manual, procedimiento, etc.
  organization_type: string # artículos, secciones, libre, etc.

  statistics:
    pages: number | null
    blocks: number
    sections: number
    hierarchy_levels: number
    has_existing_index: boolean

  file_metadata:
    last_modified: datetime
    size_bytes: number
    content_hash: string

  # Populated by "Construir índice" analysis
  structure_tree:
    - id: string
      title: string
      level: number
      role: string | null # define, clasifica, regula, recomienda, etc.
      summary: string | null
      source_ref: SourceRef
      children: [] # recursive

  analyses_completed: string[] # Which on-demand analyses have been run

  # Populated by "Preguntas que responde"
  questions_answered: string[] | null

  # Populated by "Conclusiones"
  recommendations: string[] | null

  # Populated by "Relaciones entre secciones"
  block_relations:
    - source_block_id: string
      target_block_id: string
      type: constrains | depends_on | complements | contradicts
      description: string
      source_ref: SourceRef
```


---

### 3. Clasificación y adaptación de opciones

La clasificación del documento (producida en el análisis base) **adapta el comportamiento** de las opciones disponibles, no las bloquea (dado que son pocas opciones en el MVP):

| Clasificación | Comportamiento |
|---------------|---------------|
| Normativo (reglamento, ley, política) | Todas las opciones disponibles. Análisis de bloque especialmente relevante. |
| Procedimental (manual, guía, SOP) | Todas las opciones. "Relaciones entre secciones" enfocado en flujo/secuencia. |
| Técnico (spec, arquitectura) | Todas las opciones. "Preguntas que responde" enfocado en decisiones. |
| Narrativo / sin estructura (artículo, cuento, reporte) | Solo análisis base + "Preguntas que responde" + "Conclusiones". Los análisis de nivel bloque no se ofrecen. |

La clasificación no es los 4 tipos de ADR-006 (PRD, TechSpec, PolicyProcess, Generic). Es una clasificación orientada a **qué tipo de análisis es útil**, no a qué entidades esperar.

---

### 4. Persistencia y capas acumulativas

- El **análisis base** se guarda siempre como la "ficha" del documento.
- Cada **análisis bajo demanda** enriquece el modelo guardado. No se re-ejecuta si ya existe.
- Si el documento cambia (detectable por `last_modified` + `size_bytes` en file_metadata), los análisis previos se marcan como **"posiblemente desactualizado"**. El usuario decide si re-ejecutar.
- La detección de cambio es por metadatos en el MVP. En futuras iteraciones se puede agregar comparación por content_hash.

---

### 5. Configuración del LLM

El usuario puede:

- **Seleccionar el LLM por defecto** para los análisis (Gemini, Groq, u otros disponibles).
- **Activar/desactivar auto-fallback:**
  - Si está activado: si el LLM principal falla, el sistema intenta con el fallback automáticamente e informa al usuario.
  - Si está desactivado: si el LLM falla, el sistema informa el error y ofrece reintentar o cambiar de LLM manualmente.

Esta configuración es por sesión (en el MVP). En futuras iteraciones podría ser persistente por usuario.

---

### 6. Interfaz de usuario

La UI debe proporcionar:

- **Ficha del documento** visible inmediatamente tras la carga (resultado del análisis base).
- **Panel de opciones** con los análisis disponibles, cada uno como un botón/acción que el usuario activa.
- **Indicador de estado** por cada análisis (no ejecutado / en progreso / completado / desactualizado).
- **Selector de LLM** accesible desde la interfaz (no enterrado en configuración).
- **Toggle de auto-fallback** junto al selector de LLM.

---

## Qué se mantiene de ADR-002

- El concepto de que debe existir una representación estructurada del conocimiento del documento.
- El campo `source_ref` (evidence trazable) en cada resultado — validado por ADR-004.
- Los IDs únicos referenciables para cada elemento de la estructura.
- El vocabulario de relaciones: `constrains`, `depends_on`, `contradicts` (se agrega `complements`).

## Qué se descarta de ADR-002

- La taxonomía fija de 6 tipos de elementos (propósito, conceptos, actores, reglas, procesos, restricciones) como mecanismo de comprensión.
- El Knowledge Model como "lista de entidades tipadas".
- La extracción monolítica en una sola pasada LLM.

## Qué se mantiene de ADR-006

- El mecanismo de selección híbrida (inferencia + posibilidad de ajuste).
- El vocabulario de relaciones (constrains, participates_in, depends_on, contradicts) — extendido con `complements`.

## Qué se descarta de ADR-006

- Los 4 tipos fijos (PRD, TechSpec, PolicyProcess, Generic) como clasificación.
- Los schemas de completitud (qué entidades esperar por tipo).
- La evaluación de "información faltante según schema" como concepto.

---

## Vocabulario de relaciones (actualizado)

| Tipo | Semántica | Dirección |
|------|-----------|-----------|
| constrains | Un bloque restringe o limita a otro | dirigida |
| depends_on | Un bloque depende de otro para ser válido o comprensible | dirigida |
| complements | Un bloque complementa o amplía el contenido de otro | dirigida |
| contradicts | Un bloque contradice o conflictúa con otro | bidireccional |

Se elimina `participates_in` (era específico de entity extraction: "actor participa en proceso"). Se agrega `complements` (fundamental para documentos normativos donde secciones se complementan).

---

## Impacto en features existentes

| Feature | Impacto |
|---------|---------|
| Feature 1 (Ingestion) | Sin cambios. El IR se mantiene como está. |
| Feature 2 (App Shell) | Rediseño de UI: agregar ficha, panel de opciones, selector LLM. |
| Feature 3 (Analysis Engine) | Reescritura del pipeline: nuevo análisis base + análisis bajo demanda. Se mantiene la abstracción LLM. |
| Feature 4 (Visualization) | Reescritura: de lista de entidades a ficha + árbol de estructura + resultados de análisis. |
| Feature 5 (Quality Analysis) | Se reabsorbe parcialmente en "Conclusiones y recomendaciones" del análisis bajo demanda. |
| Feature 6 (NL Queries) | Se mantiene el concepto pero opera sobre el nuevo modelo. |

---

## Riesgos

| Riesgo | Mitigación |
|--------|-----------|
| El análisis base con LLM podría ser > 5s | Usar modelo ligero (Groq), prompt mínimo (~500 tokens), timeout de 10s. Si falla, mostrar solo la parte sin LLM. |
| Los análisis bajo demanda podrían ser lentos | Cada análisis es independiente y el usuario lo solicita conscientemente. Mostrar progreso. |
| La estructura detectada podría ser incorrecta | El análisis base usa heurísticas (regex, headings). El LLM refina en "Construir índice". |
| Documentos sin estructura definida | El análisis base lo detecta y limita las opciones disponibles. |

---

## Decisiones diferidas

| Decisión | Razón |
|----------|-------|
| Detección de cambio por content hash | Optimización futura; metadatos suficientes para MVP |
| Persistencia de preferencia de LLM por usuario | Requiere autenticación; en MVP es por sesión |
| Análisis de nivel bloque detallado | Se implementa después de validar que el análisis de nivel documento funciona |
| Comparación multi-documento | Siguiente etapa, una vez que la estructura individual se guarda correctamente |
