# ADR-008: LLM Context Caching para On-Demand Analysis

**Estado:** Propuesto (mejora futura)
**Fecha:** 2026-07-26

## Contexto

El sistema on-demand analysis (C3) envía el documento completo al LLM en cada análisis individual. Si el usuario ejecuta las 4 opciones, el documento se transmite 4 veces, generando:

- Latencia acumulada (30-60s por llamada con documentos largos)
- Costo de tokens de entrada multiplicado x4
- Timeouts en documentos grandes

## Alternativas evaluadas

| Opción | Descripción | Pros | Contras |
|--------|-------------|------|---------|
| A. Gemini File API | Subir documento a Google, referenciar por URI en cada prompt | Reduce tokens x4, 48h de retención | Acoplamiento a Gemini, no funciona en fallback |
| B. Context Caching | Crear cached content con el documento, enviar solo instrucciones | Menor latencia, menor costo | API específica de Gemini, gestión de expiración |
| C. Multi-prompt único | Pedir los 4 análisis en una sola llamada | 1 sola llamada | Fallo parcial pierde todo, respuesta enorme |
| D. Batch al primer trigger | Ejecutar los 4 análisis juntos internamente | Transparente al usuario | Paga por análisis no solicitados |

## Decisión propuesta

Implementar **Opción B (Context Caching)** como optimización prioritaria:

1. Al completar la ingesta base, crear un cached content en Gemini con el IR del documento
2. Almacenar el `cache_id` en la tabla `documents` o `analysis_results`
3. Los analyzers on-demand referencian el cache en vez de enviar el texto completo
4. Invalidar/recrear el cache si el documento se re-sube
5. Mantener el flujo actual como fallback si el cache expira o el modelo de fallback no soporta caching

## Consecuencias esperadas

- Reducción de ~75-90% en tokens de entrada para llamadas 2-4
- Latencia reducida a 5-15s (como estimaba el diseño original)
- Complejidad adicional: gestión de lifecycle del cache, invalidación en re-upload

## Prerrequisitos

- Validar disponibilidad de Context Caching en el tier de Gemini usado
- Definir estrategia de fallback cuando el cache no está disponible
