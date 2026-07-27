---
inclusion: auto
---

# Spec Structure — Document Intelligence

## Ubicación y organización

- Los specs se crean en `.kiro/specs/<nombre-del-spec>/`.
- Cada spec contiene exactamente tres archivos: `requirements.md`, `design.md`, `tasks.md`.
- Los specs referencian documentación existente, no la duplican.

## requirements.md

Estructura obligatoria:

```markdown
# Requirements Document

<Nombre del Feature>

## Introduction
Descripción del feature, contexto, qué problema resuelve.

## Relevant Documentation
Lista de referencias con #[[file:path]] a docs, ADRs, código existente.

## Feature Boundaries
**In scope:** / **Out of scope:**

## Glossary
| Term | Definition |
|------|------------|
| Term_Name | Descripción |

---

## Requirements

### Requirement N: Nombre

**User Story:** As a [role], I want [goal] so that [benefit].

#### Acceptance Criteria
1. WHEN [condition], THE system SHALL [behavior].
2. IF [condition], THEN THE system SHALL [behavior].

**Traceability:**
- Referencia a PRD, ADR, o decisión de diseño.
```

## design.md

Estructura obligatoria:

```markdown
# Design — <Nombre del Feature>

## Overview
## Relevant Documentation
## Architecture
## Components and Interfaces
## Data Models
## API Design
## Key Technical Decisions
## Correctness Properties
## Interaction Flow
## Error Handling
## Security Considerations
## Testing Strategy
## Dependencies
## File Structure
## Traceability to Requirements
```

### Correctness Properties — Formato obligatorio

Cada propiedad debe usar exactamente este formato para la referencia de validación:

```markdown
### Property N: Nombre

*For any* [condición], [el sistema] SHALL [propiedad garantizada].

**Validates: Requirements X.Y, X.Z**
```

Donde:
- `X` = número del requirement (1, 2, 3...)
- `Y` = número del criterio de aceptación dentro de ese requirement (1, 2, 3...)
- Siempre usar "Requirements" (plural), incluso para una sola referencia
- Siempre usar formato número.número (e.g., `3.4` = Requirement 3, criterion 4)
- Múltiples referencias separadas por coma: `Requirements 2.6, 2.7`

Ejemplos correctos:
- `**Validates: Requirements 2.3**`
- `**Validates: Requirements 1.2, 1.3**`
- `**Validates: Requirements 3.4, 1.4**`

Ejemplos incorrectos (producen warnings):
- `**Validates: Requirement 2 (criterion 3)**` — no usar paréntesis ni singular
- `**Validates: Req 3, criteria 1, 6**` — no abreviar ni usar "criteria"

## tasks.md

Estructura obligatoria:

```markdown
# Implementation Plan: <Nombre del Feature>

## Overview
Descripción breve del plan de implementación.

## Tasks

- [ ] 1. Nombre de la task
  - [ ] 1.1 Nombre del subtask
    - Descripción detallada de lo que hay que hacer
    - _Requirements: Req N (criteria M, P)_

## Notes
Notas relevantes sobre dependencias, restricciones, orden.

## Task Dependency Graph
```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1", "2.2"] }
  ]
}
```
```

### Convenciones de tasks

- Cada task tiene subtasks con checkbox `- [ ]`.
- Los subtasks referencian requirements con `_Requirements: Req N (criteria M)_`.
- El dependency graph define waves de ejecución paralela.
- Tasks completadas usan `- [x]`.

## Convenciones generales

- La documentación de specs es en español (descripciones) e inglés (código, interfaces).
- Los specs referencian archivos con `#[[file:relative/path]]`.
- Un spec por feature/capacidad.
- Los specs no se modifican después de implementados (se crean nuevos si la feature evoluciona, o se marcan como referencia histórica).
