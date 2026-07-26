# Retrospectiva 001 — Desconexión entre visión de producto e implementación del Knowledge Model

> Fecha: 2026-07-26
> Tipo: Post-mortem de diseño
> Estado: Documento de aprendizaje
> Impacto: Features 3, 4, 5 — requieren rediseño conceptual

---

## Resumen ejecutivo

La implementación actual de Document Intelligence no cumple con la intención original del producto. Lo que se esperaba era una herramienta que ayudara a **comprender la estructura de documentos rápidamente** — un mapa estructural que permitiera entender qué hace el documento, cómo está organizado, y cómo sus partes se relacionan, sin necesidad de leerlo completo. Lo que se construyó fue un **extractor de entidades** que produce una lista larga de elementos clasificados en 6 categorías, sin preservar la estructura del documento ni ofrecer una comprensión progresiva.

---

## ¿Qué se esperaba?

El objetivo de la herramienta era:

1. **Comprender documentos rápidamente sin leerlos** — ver de qué trata, cómo está organizado, qué preguntas responde.
2. **Análisis progresivo** — una primera salida rápida (resumen, clasificación, estructura) y luego opciones para profundizar bajo demanda.
3. **Preservar la estructura del documento** — secciones, artículos, bloques, jerarquía — como un mapa navegable.
4. **Identificar relaciones entre bloques** — qué depende de qué, qué se complementa, qué se contradice.
5. **Guardar el conocimiento estructural** — para que al agregar un segundo documento se puedan detectar dependencias, contradicciones y complementos entre documentos.
6. **Interacción con opciones** — el usuario decide qué análisis ejecutar, no todo de golpe.

La visión a largo plazo: documentos alineados y sincronizados (reglamentos, políticas, manuales) donde modificar uno sugiera cambios en los demás.

---

## ¿Qué se construyó?

Un pipeline que:

1. Toma el documento completo.
2. Lo envía al LLM en una sola llamada masiva (30-90 segundos).
3. Le pide extraer **todas** las entidades que encajen en 6 categorías predefinidas (propósito, conceptos, actores, reglas, procesos, restricciones).
4. Muestra el resultado como una lista agrupada por tipo.
5. No preserva la estructura del documento.
6. No ofrece opciones — todo es automático.
7. La interfaz no tiene menú, selección de modelo, ni acciones configurables.

---

## Tabla comparativa

| Aspecto | Esperado | Construido |
|---------|----------|-----------|
| Primera vista | Resumen de 2-3 líneas + clasificación + estructura | Lista de entidades tipadas |
| Velocidad | < 5 segundos para lo básico | 30-90 segundos para todo |
| Estructura | Mapa de secciones con roles funcionales | No existe — el documento pierde su organización |
| Análisis | Progresivo, bajo demanda, por bloques | Todo de golpe, una sola llamada |
| Relaciones | Entre bloques/secciones del documento | Entre entidades atómicas extraídas |
| Interacción | Menú de opciones, análisis selectivo | Sin opciones — flujo automático fijo |
| Qué se guarda | Estructura del documento como mapa de conocimiento | Lista plana de entidades con source_ref |
| Preparación multi-doc | Mapa de estructura comparable entre documentos | Entidades sin contexto estructural |

---

## ¿Dónde se produjo la desconexión?

### Punto de quiebre: ADR-002 (Knowledge Model)

La ADR-002 tomó la decisión de representar el conocimiento como **"elementos tipados con relaciones opcionales"**. Esta decisión convirtió la comprensión documental en extracción de entidades.

La ADR discutió tres alternativas:
1. Lista plana de elementos tipados
2. Grafo de conocimiento
3. **Modelo híbrido (la elegida):** elementos tipados con relaciones opcionales

Las tres alternativas comparten el mismo supuesto fundamental erróneo: que el objetivo es **extraer entidades** del documento (conceptos, actores, reglas). Ninguna alternativa discutió:

- Preservar la estructura del documento (secciones, jerarquía, organización)
- Análisis progresivo (primero lo rápido, luego el detalle)
- El rol funcional de cada bloque (define, clasifica, establece procedimientos)
- Qué preguntas responde cada sección
- La interacción del usuario con el análisis

**La ADR resolvió un problema de modelado de datos ("¿JSON o grafo?") sin resolver primero el problema de producto ("¿qué necesita ver el usuario para comprender el documento?").**

### Cascada del error

```
ADR-002: Knowledge Model = lista de entidades tipadas 
↓ 
ADR-006: Tipos de documento = schemas de "qué entidades esperar" 
↓ 
Feature 3 (Extraction): Prompt que extrae "cosas" de 6 categorías fijas 
↓ 
Feature 4 (Visualization): Lista agrupada por tipo sin estructura documental 
↓ 
Feature 5 (Quality): Busca "qué falta" contra un schema de entidades esperadas 
↓ 
Resultado: Una lista larga de ideas encontradas sin contexto estructural
```

### El PRD contribuyó al problema

El PRD v0.6, en su flujo principal (paso 7), prescribió la solución:

> "La IA identifica elementos relevantes: propósito, conceptos, actores, reglas, procesos, restricciones"

Esto ya es una implementación, no un requisito. Un requisito habría sido:

> "El usuario puede comprender la estructura y contenido de un documento sin leerlo completo"

Al prescribir los 6 tipos de elementos como la forma de "comprender", el PRD cerró el espacio de soluciones antes de que se explorara el problema real.

### El MVP Spec reforzó el error

La Spec formalizó las User Stories alrededor de la taxonomía fija:

- US-002: "Quiero que el sistema genere un Knowledge Model del documento para comprender su estructura de conocimiento (propósito, conceptos, actores, reglas, procesos, restricciones y sus relaciones)."

La User Story confunde "estructura de conocimiento" con "lista de entidades". La estructura del conocimiento de un documento normativo no son sus conceptos individuales — es cómo está organizado, qué establece cada sección, y cómo se relacionan los bloques entre sí.

---

## Causas raíz

### 1. Se confundió "conocimiento" con "entidades"

El conocimiento de un documento normativo no es una lista de conceptos, actores y reglas. Es:
- Su propósito y alcance
- Cómo está organizado (estructura)
- Qué rol juega cada parte (define, regula, establece, recomienda)
- Qué preguntas responde
- Cómo se relacionan sus partes entre sí

### 2. Se optimizó para el modelo de datos, no para la experiencia

Las ADRs discutieron exhaustivamente cómo almacenar el resultado (JSON, grafo, híbrido) sin discutir primero qué resultado necesitaba el usuario.

### 3. Se perdió el "progresivo" y "bajo demanda"

La arquitectura asume que todo se analiza de golpe. No hay concepto de:
- Análisis rápido vs profundo
- El usuario eligiendo qué analizar
- Resultados incrementales

### 4. Se perdió la estructura del documento

El pipeline de extracción envía todo el texto al LLM y le pide que encuentre entidades. El resultado es una bolsa de entidades sin contexto de dónde estaban en el documento ni qué rol cumplían.

### 5. La taxonomía fija limitó la comprensión

Las 6 categorías (propósito, conceptos, actores, reglas, procesos, restricciones) son categorías de NLP/entity extraction, no categorías de comprensión documental. Un usuario que analiza un reglamento necesita saber:
- "Esta sección define términos"
- "Esta sección establece procedimientos en 4 fases"
- "El artículo 25 contradice parcialmente el artículo 12"

No necesita saber: "encontré un concepto llamado X" × 50.

### 6. No se definió la interacción del usuario

Ningún documento de diseño describió cómo el usuario interactúa con los resultados. Se asumió que mostrar la lista sería suficiente.

---

## ¿Qué se hizo bien?

No todo está mal. La infraestructura construida tiene valor:

- **Pipeline de ingesta** — funciona bien, soporta 3 formatos, produce un IR limpio con chunks y contexto estructural
- **Abstracción LLM** — LiteLLM con fallback está correctamente implementada
- **Verificación de evidencia** — el concepto de Trust by Evidence y source_ref es correcto
- **Arquitectura modular** — el desacoplamiento permite reemplazar componentes
- **Frontend scaffolding** — React + Zustand + Tailwind + shadcn/ui está listo para construir encima
- **Modelo de confianza (ADR-004)** — la idea de que todo sea trazable al documento es valiosa
- **Modelo de privacidad (ADR-005)** — el consentimiento y la abstracción de proveedor están bien

El problema no es la calidad técnica — es que se construyó lo incorrecto.

---

## ¿Qué debió hacerse diferente?

### En la fase de Product Discovery

1. **Definir la interacción antes del modelo de datos** — ¿Qué ve el usuario? ¿Qué puede hacer? ¿Cuál es el primer resultado que ve?
2. **Prototipar la experiencia** — Un mockup de "así se ve cuando subes un reglamento" habría revelado que una lista de entidades no es lo que se necesitaba.
3. **Separar "análisis rápido" de "análisis profundo"** — Dos flujos, no uno monolítico.

### En las ADRs

4. **Definir primero qué es "comprender un documento"** antes de decidir cómo almacenarlo.
5. **Incluir la estructura del documento como ciudadano de primera clase** — no solo el texto sino la organización.
6. **Cuestionar la taxonomía de 6 tipos** — ¿son esas categorías las que necesita un usuario de documentos normativos?

### En la implementación

7. **Empezar con el resultado más rápido y simple** — resumen + clasificación en < 5s — y luego agregar análisis.
8. **Preservar la estructura del documento en el IR** — los chunks ya tienen contexto estructural, pero se ignora en la extracción.
9. **Diseñar la UI con opciones desde el inicio** — no un flujo automático sin interacción.

---

## Impacto y siguiente paso

### Qué se mantiene
- Feature 1 (Document Ingestion) — intacta
- Feature 2 (App Shell & Upload) — se modifica la UI pero el scaffolding se mantiene
- Infraestructura backend (FastAPI, Supabase, LiteLLM)
- Modelo de privacidad y consentimiento
- Concepto de Trust by Evidence (source_ref)

### Qué se rediseña
- El concepto de "Knowledge Model" — debe incluir estructura documental, no solo entidades
- El pipeline de análisis — debe ser progresivo, no monolítico
- El prompt de extracción — debe entender estructura, no solo extraer entidades
- La UI de resultados — necesita opciones, menú, análisis bajo demanda
- La clasificación de documentos — debe determinar qué análisis profundos están disponibles

### Documentos a crear/revisar
- PRD v2 — redefinir capacidades centradas en comprensión estructural
- ADR-007 — Redefinición del análisis: de extracción de entidades a comprensión estructural progresiva
- Nuevas specs para el pipeline rediseñado
- Steering files actualizados

---

## Lecciones aprendidas

1. **El modelo de datos no es el producto.** Discutir si usar JSON o grafo no resuelve qué necesita el usuario.
2. **Definir la experiencia antes de la arquitectura.** ¿Qué ve el usuario primero? ¿Qué opciones tiene?
3. **Progresivo > monolítico.** Un resultado rápido e imperfecto es más valioso que un resultado perfecto que tarda 90 segundos.
4. **La estructura del documento ES el conocimiento.** Para documentos normativos, la organización (artículos, secciones, capítulos) es tan importante como el contenido.
5. **Las taxonomías genéricas no sirven para dominios específicos.** "Concepto, actor, regla" es demasiado genérico para quien analiza reglamentos.
6. **Sin interacción no hay herramienta.** Un flujo automático sin opciones es un script, no un producto.
