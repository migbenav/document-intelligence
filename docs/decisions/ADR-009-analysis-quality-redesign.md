# ADR-009: Rediseño de Calidad del Análisis On-Demand

**Estado:** Aprobado
**Fecha:** 2026-07-27

## Contexto

La implementación actual de los análisis on-demand (C3 v1) presenta problemas fundamentales de calidad que impiden que la aplicación cumpla su propósito:

1. **Build Index lista encabezados** en lugar de comprender la organización funcional del documento. Si un documento tiene "Misión", "Visión", "Objetivos" como secciones separadas, el sistema las lista individualmente en vez de agruparlas bajo "Propósito del documento".

2. **Questions Answered genera preguntas sobre contenido** ("¿Qué dice el capítulo 3?") en lugar de revelar la lógica del documento ("¿Puede hacerse? → ¿Quién lo decide? → ¿Cómo se ejecuta?").

3. **Conclusions produce contradicciones incoherentes** entre dominios independientes (ej: reglas de estacionamiento vs. reglas de ascensores). No identifica problemas reales como mezcla de propósitos (procedimientos dentro de documentos normativos).

4. **Section Relations genera relaciones triviales** en lugar de conexiones funcionales (qué habilita qué, qué restringe qué).

5. **El modelo real usado no se propaga al frontend**, el error de cuota es indistinguible de otros errores, y el fallback no funciona porque los tres modelos por defecto apuntan a Gemini.

## Decisión

### Cambio fundamental en la filosofía de análisis

**Antes:** Los análisis describen la estructura visual del documento (encabezados, secciones, contenido).

**Después:** Los análisis comprenden el PROPÓSITO FUNCIONAL del documento y cómo sus partes sirven a ese propósito.

### Cambios específicos

#### 1. Prompts rediseñados (v2)

Cada prompt cambia de "lista lo que ves" a "comprende lo que el documento HACE":

- **build-index-v2:** Identifica agrupaciones funcionales (no encabezados). Nivel 1 = funciones del documento, contenido = capítulos que sirven a esa función.
- **questions-answered-v2:** Genera preguntas que revelan la cadena lógica/decisional del documento, adaptadas al tipo (normativo, procedimental, narrativo).
- **conclusions-v2:** Identifica dominios primero, luego busca problemas DENTRO de cada dominio. Detecta mezcla de propósitos.
- **section-relations-v2:** Identifica relaciones funcionales (enables, restricts, requires, implements) no secuenciales.

#### 2. Clasificación como input obligatorio

Todos los analyzers reciben la clasificación del document_card como contexto. El prompt se adapta según si el documento es normativo, procedimental, narrativo, o genérico.

#### 3. Transparencia de modelo

- Los analyzers retornan el `model_id` real (de `LLMResponse.model_id`), no el modelo solicitado.
- Errores de cuota se clasifican separadamente (HTTP 429) con mensaje específico.
- El fallback por defecto cambia a Groq (diferente provider que el primario Gemini).

#### 4. Detección de idioma mejorada

- Muestra expandida a 2000 caracteres.
- Soporte para portugués y francés.
- Confirmación por LLM cuando la detección local tiene baja confianza.

### Compatibilidad

Todos los cambios son backward-compatible:
- Nuevos campos en modelos Pydantic/TypeScript son opcionales con defaults.
- Resultados existentes (prompt v1) siguen siendo válidos y visualizables.
- La tabla `analysis_results` no requiere migración (JSONB absorbe nuevos campos).
- Los endpoints mantienen la misma firma (campos adicionales en response).

## Alternativas evaluadas

| Opción | Descripción | Decisión |
|--------|-------------|----------|
| Mejorar prompts v1 incrementalmente | Ajustar instrucciones sin cambiar estructura | Rechazada — el problema es conceptual, no de redacción |
| Agregar paso de "comprensión" previo | Ejecutar una llamada LLM extra antes del análisis para entender el doc | Rechazada — duplica latencia y costo |
| Usar Build Index como base obligatoria para todos | Forzar Build Index antes de cualquier otro análisis | Rechazada — agrega fricción al usuario |
| Prompt v2 con clasificación como contexto | Rediseñar prompts con enfoque funcional + clasificación | **Aprobada** |

## Consecuencias

### Positivas
- Los análisis producen insights accionables (no listas de encabezados).
- Las recomendaciones son coherentes y relevantes.
- El usuario sabe qué modelo se usó y por qué falló.
- El fallback funciona correctamente entre providers.

### Negativas / Riesgos
- Los resultados v2 pueden ser diferentes a v1 para el mismo documento — el usuario podría notar el cambio.
- La calidad depende de la clasificación correcta del document_card; si la clasificación es incorrecta, los prompts adaptativos pueden generar resultados subóptimos.
- Agregar `classification` como dependencia introduce acoplamiento entre base analysis y on-demand analysis.

### Mitigaciones
- Resultados v1 existentes no se borran ni invalidan — el usuario puede re-analizar para obtener v2.
- La clasificación "generic" funciona como fallback conservador si el card es parcial.
- El `prompt_version` en cada resultado permite al frontend saber qué versión produjo el resultado.

## Referencias

- Spec: `.kiro/specs/analysis-quality-v2/`
- Spec original: `.kiro/specs/on-demand-analysis/`
- ADR-007: Rediseño de análisis estructural (define el modelo progresivo)
- ADR-004: Modelo de confianza (source_ref se mantiene)
