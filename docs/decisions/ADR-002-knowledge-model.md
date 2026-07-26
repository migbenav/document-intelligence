# ADR-002 — Modelo de representación del conocimiento (Knowledge Model)

> Estado: **Superseded partially by ADR-007**
> Fecha: 2026-07-23
> Aprobada: 2026-07-23
> Depende de: ADR-001-mvp-scope.md (aprobada)

---

# Contexto

La ADR-001 estableció que el MVP trabajará con un único documento y producirá:

1. Extracción de conocimiento estructurado.
2. Detección de inconsistencias internas.
3. Identificación de información faltante según estructura esperada.
4. Sugerencias de mejora.
5. Consulta por lenguaje natural.

Todas estas capacidades dependen de una representación intermedia del conocimiento. Sin embargo, esa representación no está definida en ningún documento del proyecto. Tres observaciones de la revisión arquitectónica lo señalan:

**OBS-03 — No se define qué es la "representación estructurada del conocimiento"**

Es el artefacto central del sistema. Aparece mencionado en la Product Vision, el PRD y la spec, pero ninguno define su estructura, formato ni contenido concreto. Sin esta definición no se puede diseñar almacenamiento, consultas, visualización ni evaluación de calidad.

**OBS-14 — No se documenta si la taxonomía es fija o configurable**

La spec lista los elementos a extraer (propósito, conceptos, actores, reglas, restricciones) como si fueran fijos. No se discute si un usuario podrá personalizar qué se extrae según el tipo de documento. Esto impacta la extensibilidad del sistema y su aplicabilidad a diferentes dominios.

**OBS-17 — Inconsistencia en la taxonomía entre PRD y spec**

El PRD (C2) incluye "procesos" como elemento a extraer. La spec (RF-03) no lo lista. Es una inconsistencia menor pero que impide tener una fuente de verdad única sobre qué extrae el sistema.

---

# Problema

¿Cómo debe representar el MVP el conocimiento extraído de un documento?

Específicamente:

1. ¿Qué estructura tiene el modelo de conocimiento?
2. ¿Qué elementos (tipos de nodos) componen la taxonomía?
3. ¿Existen relaciones entre esos elementos?
4. ¿La taxonomía es fija para el MVP o configurable por tipo de documento?
5. ¿Qué formato de datos se utiliza para almacenar y consultar el modelo?

---

# Alternativas consideradas

---

## Alternativa 1 — Lista plana de elementos tipados (JSON estructurado)

**Descripción**

El modelo de conocimiento se representa como un documento JSON con secciones fijas, una por cada tipo de elemento. No se modelan relaciones explícitas entre elementos. Cada elemento tiene un tipo, un contenido textual y opcionalmente una referencia a la ubicación en el documento fuente.

Estructura conceptual:

```
{
  "document_type": "PRD",
  "purpose": "...",
  "concepts": [ { "name": "...", "description": "...", "source_ref": "..." } ],
  "actors": [ ... ],
  "rules": [ ... ],
  "processes": [ ... ],
  "constraints": [ ... ]
}
```

Taxonomía: fija en el MVP. Los tipos de elementos son: propósito, conceptos, actores, reglas, procesos, restricciones.

**Ventajas**

- Simplicidad máxima de implementación.
- Fácil de serializar, almacenar y consultar.
- Bajo costo de procesamiento.
- La estructura es directamente comprensible para el usuario sin necesidad de visualización compleja.
- Ideal para un primer MVP que necesita validar rápido.

**Desventajas**

- No captura relaciones entre elementos (un actor que participa en un proceso, una regla que restringe un concepto).
- Limitada para la detección de inconsistencias, que a menudo requiere cruzar información entre tipos.
- Escalar hacia análisis multi-documento en el futuro requiere refactorizar la estructura.
- No soporta análisis de dependencias internas.

**Impacto técnico**

Bajo. Almacenamiento en JSON/documento. Consultas simples sobre propiedades. Sin necesidad de motor de grafos ni lógica relacional.

**Impacto en evolución futura**

Limitado. Migrar a una estructura relacional o de grafo requerirá transformar el modelo existente. No es imposible, pero implica una migración.

---

## Alternativa 2 — Grafo de conocimiento tipado (nodos y relaciones)

**Descripción**

El modelo se representa como un grafo donde cada elemento extraído es un nodo tipado y las conexiones entre elementos son aristas con tipo y dirección. Esto permite modelar explícitamente las relaciones semánticas entre conceptos.

Estructura conceptual:

```
Nodos:
  { id, type: "concept", name, description, source_ref }
  { id, type: "actor", name, description, source_ref }
  { id, type: "rule", name, description, source_ref }
  ...

Relaciones:
  { source_id, target_id, type: "participates_in" }
  { source_id, target_id, type: "constrains" }
  { source_id, target_id, type: "contradicts" }
  ...
```

Taxonomía de nodos: propósito, conceptos, actores, reglas, procesos, restricciones (fija en MVP).
Taxonomía de relaciones: participación, restricción, dependencia, contradicción (extensible).

**Ventajas**

- Captura las relaciones semánticas entre elementos, habilitando detección de inconsistencias por cruce.
- Es la representación natural para el análisis de calidad documental (contradicciones = relaciones de tipo conflicto).
- Escala naturalmente hacia análisis multi-documento (unir grafos de distintos documentos).
- Permite visualización como grafo interactivo.
- Alineada con la visión a largo plazo del producto.

**Desventajas**

- Mayor complejidad de implementación: requiere definir tipos de relaciones, lógica de inferencia y almacenamiento relacional o de grafos.
- Mayor costo de extracción: el LLM debe identificar no solo elementos sino también sus relaciones.
- Riesgo de sobre-ingeniería para un MVP que trabaja con un solo documento.
- El LLM puede generar relaciones incorrectas (alucinaciones de relaciones), aumentando el ruido.

**Impacto técnico**

Medio-alto. Requiere un modelo de datos para nodos y relaciones, lógica de traversal para detección de inconsistencias, y una capa de visualización capaz de renderizar grafos.

**Impacto en evolución futura**

Alto. El modelo de grafo es directamente extensible a multi-documento sin migración. Agregar un segundo documento es agregar nodos y relaciones al grafo existente.

---

## Alternativa 3 — Modelo híbrido: elementos tipados con relaciones opcionales

**Descripción**

Combina la simplicidad de la Alternativa 1 con la capacidad relacional de la Alternativa 2. El modelo base es una lista de elementos tipados (como Alternativa 1), pero cada elemento puede tener relaciones opcionales con otros elementos del mismo documento.

Estructura conceptual:

```
{
  "document_type": "PRD",
  "purpose": { "content": "...", "source_ref": "..." },
  "elements": [
    {
      "id": "e1",
      "type": "concept",
      "name": "...",
      "description": "...",
      "source_ref": "...",
      "relations": [
        { "target_id": "e5", "type": "constrained_by" }
      ]
    },
    ...
  ],
  "quality_analysis": {
    "inconsistencies": [ ... ],
    "missing_elements": [ ... ],
    "suggestions": [ ... ]
  }
}
```

Taxonomía de elementos: fija en el MVP (propósito, conceptos, actores, reglas, procesos, restricciones).
Relaciones: opcionales, extraídas cuando el LLM las identifica con suficiente confianza.

**Ventajas**

- Mantiene la simplicidad del JSON plano para almacenamiento y serialización.
- Permite capturar relaciones cuando existen, sin forzar su extracción en todos los casos.
- El análisis de calidad (inconsistencias, faltantes, sugerencias) se modela como una sección separada del resultado.
- Escala razonablemente hacia multi-documento: los elementos ya tienen IDs referenciables.
- Menor riesgo de alucinaciones en relaciones porque son opcionales (el sistema no se fuerza a encontrarlas).
- La taxonomía de elementos es fija, pero la estructura permite agregar nuevos tipos sin romper el esquema.

**Desventajas**

- No tiene la pureza de un grafo completo: los algoritmos de traversal son ad-hoc en lugar de usar un motor de grafos.
- El modelo no impone completitud en las relaciones, lo que puede generar grafos parciales difíciles de interpretar.
- Es un compromiso que puede resultar insuficiente si el producto necesita análisis relacional profundo rápidamente.

**Impacto técnico**

Medio. Almacenamiento en JSON/documento con IDs referenciables. Las relaciones son propiedades de cada elemento. No requiere motor de grafos pero permite lógica de cruce básica.

**Impacto en evolución futura**

Medio-alto. La estructura con IDs y relaciones opcionales puede migrar hacia un grafo completo sin pérdida de información. Agregar multi-documento requiere un índice cruzado pero no reestructurar el modelo base.

---

# Sobre la taxonomía

Independientemente de la alternativa elegida, la taxonomía de elementos a extraer debe unificarse entre documentos.

**Propuesta de taxonomía unificada para el MVP (resuelve OBS-17):**

- Propósito
- Conceptos
- Actores
- Reglas
- Procesos
- Restricciones

Esta lista incorpora "procesos" (presente en el PRD pero ausente en la spec) y mantiene todos los elementos ya acordados.

**Sobre si es fija o configurable (resuelve OBS-14):**

Para el MVP se recomienda una taxonomía fija. La configurabilidad por tipo de documento puede agregarse en una iteración posterior sin impacto arquitectónico significativo, siempre que el modelo use tipos como strings o enums extensibles en lugar de columnas hard-coded.

---

# Recomendación

**Alternativa 3 — Modelo híbrido: elementos tipados con relaciones opcionales.**

**Razonamiento:**

1. El MVP necesita detectar inconsistencias internas. Esto requiere poder cruzar información entre elementos (por ejemplo: una regla que contradice otra regla, o un actor mencionado en un proceso pero ausente de la lista de actores). La Alternativa 1 no soporta esto sin lógica ad-hoc externa al modelo.

2. El MVP no necesita un motor de grafos completo. Trabajamos con un solo documento y las relaciones serán limitadas en número. La Alternativa 2 introduce complejidad prematura.

3. El modelo híbrido permite que el análisis de calidad (inconsistencias, faltantes, sugerencias) viva como una sección derivada del modelo, facilitando su presentación al usuario.

4. Los IDs y relaciones opcionales preparan la estructura para multi-documento sin requerir migración.

5. La taxonomía fija con tipos extensibles (string/enum) permite agregar configurabilidad por tipo de documento en el futuro sin romper el esquema.

**Pre-requisitos si se aprueba:**

- Definir el JSON Schema formal del modelo de conocimiento.
- Definir los tipos de relaciones soportados en el MVP.
- Definir la estructura de `quality_analysis` (inconsistencies, missing_elements, suggestions).

---

# Decisión final

**Decisión aprobada: Alternativa 3 — Modelo híbrido: elementos tipados con relaciones opcionales.**

## Resumen de la decisión

El Knowledge Model del MVP se representa como una colección de elementos tipados con relaciones opcionales entre ellos. Cada elemento tiene un ID único, un tipo de la taxonomía fija, contenido textual, y una referencia de evidencia flexible (`source_ref`) que permite trazarlo hasta el documento original.

## Taxonomía aprobada (fija en el MVP)

- Propósito
- Conceptos
- Actores
- Reglas
- Procesos
- Restricciones

La taxonomía es fija para el MVP. La estructura utiliza tipos extensibles (strings) que permiten agregar configurabilidad por tipo de documento en iteraciones futuras sin romper el esquema.

## Relaciones

Las relaciones entre elementos son opcionales. Se capturan cuando el sistema las identifica con suficiente confianza. Los tipos de relaciones soportados en el MVP se definirán durante la etapa de diseño.

## Análisis de calidad

El resultado del análisis de calidad (inconsistencias internas, información faltante, sugerencias de mejora) se modela como una sección derivada del Knowledge Model, separada de los elementos extraídos.

## Referencia de evidencia (source_ref)

Cada elemento incluye un campo `source_ref` definido como una referencia de evidencia flexible que contiene la información disponible según el formato del documento de origen (document_id, page, section, chunk_id, evidence text span). No se asumen referencias basadas en líneas. La definición detallada de `source_ref` fue refinada en ADR-004.

## Documentos actualizados

Los siguientes documentos fueron actualizados para reflejar esta decisión:

- `.specs/001-foundation/spec.md` — taxonomía unificada en RF-03, estructura del modelo documentada.
- `docs/product/03-prd.md` — C2 alineado con la taxonomía y el concepto de Knowledge Model.

