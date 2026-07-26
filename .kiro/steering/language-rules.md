---
inclusion: auto
---

# Reglas de Idioma — Document Intelligence

## Principio general

La aplicación tiene un **idioma de interfaz seleccionado por el usuario** (`ui_language`) que determina cómo se presenta la información. El **idioma del documento** (`document_language`) se detecta automáticamente durante la ingesta y se usa solo donde corresponde.

## Reglas por tipo de contenido

| Tipo de contenido | Idioma a usar | Ejemplos |
|---|---|---|
| Labels, botones, navegación, tags | `ui_language` | "Resumen", "Clasificación: Normativo", "Reintentar" |
| Resumen ejecutivo / summary | `ui_language` | Documento en inglés → resumen en español si `ui_language=es` |
| Explicaciones de análisis | `ui_language` | "Este bloque define las reglas de..." |
| Clasificaciones y categorías | `ui_language` | "Normativo", "Guía", "Manual" |
| Texto extraído / citas / evidencia | `document_language` | Se muestra tal cual aparece en el documento |
| Sugerencias de cambio / contenido faltante | `document_language` | Para que el usuario pueda integrarlas al documento directamente |
| Preguntas generadas sobre el documento | `ui_language` | Las preguntas son para el usuario, no para el documento |

## Reglas para prompts LLM

- Todo prompt al LLM debe incluir una instrucción explícita de idioma de respuesta.
- El idioma de respuesta depende del tipo de output esperado (ver tabla arriba).
- El prompt en sí puede estar en inglés (para mejor performance del modelo).
- Las variables del código permanecen en inglés siempre.

Formato de instrucción en prompts:
```
Respond in {ui_language}. // para resúmenes, explicaciones, clasificaciones
Respond in {document_language}. // para sugerencias de contenido
```

## Idiomas soportados (MVP)

- Español (`es`) — idioma por defecto
- Inglés (`en`)

## Propagación

- El `ui_language` se almacena como preferencia del usuario (localStorage en frontend).
- Se envía al backend como header (`Accept-Language`) o query parameter en cada request que involucre LLM.
- El `document_language` ya existe en el IR metadata (detectado por el ingestion layer).
- Ambos valores están disponibles en el contexto de cada prompt.
