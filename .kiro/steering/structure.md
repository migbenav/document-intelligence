---
inclusion: auto
---

# Repository Structure — Document Intelligence

## Organización del repositorio

```
document-intelligence/
├── .github/workflows/       → CI/CD workflows
├── .kiro/
│   ├── steering/            → Steering files (contexto permanente para Kiro)
│   └── specs/               → Kiro Specs (features a implementar)
├── docs/
│   ├── architecture/        → Documentación de arquitectura técnica
│   ├── assets/              → Recursos gráficos y diagramas
│   ├── decisions/           → ADRs (Architecture Decision Records)
│   ├── deployment/          → Documentación de despliegue
│   ├── design/              → Documentos de diseño técnico
│   ├── methodology/         → Metodología de trabajo (PEM)
│   └── product/             → Documentación de producto (visión, PRD, spec)
├── infrastructure/          → Infraestructura como código
├── scripts/                 → Scripts de utilidad
├── src/
│   ├── backend/             → Código del servidor y pipeline de análisis
│   ├── frontend/            → Código de la interfaz de usuario
│   └── shared/              → Código compartido entre backend y frontend
└── tests/
    ├── e2e/                 → Tests end-to-end
    ├── integration/         → Tests de integración
    └── unit/                → Tests unitarios
```

## Documentación

- La documentación de producto vive en `docs/product/`.
- Las decisiones arquitectónicas se registran en `docs/decisions/` como ADR.
- El diseño técnico se documenta en `docs/design/`.
- La documentación de arquitectura de sistema en `docs/architecture/`.
- La metodología del proyecto en `docs/methodology/`.

## Specs

- Los Kiro Specs se crean en `.kiro/specs/`.
- Cada spec corresponde a una feature o capacidad a implementar.
- Las specs referencian la documentación existente, no la duplican.

## Código

- Backend en `src/backend/`.
- Frontend en `src/frontend/`.
- Código compartido (tipos, interfaces, constantes) en `src/shared/`.

## Tests

- Unit tests para lógica aislada en `tests/unit/`.
- Integration tests para interacción entre componentes en `tests/integration/`.
- E2E tests para flujos completos del usuario en `tests/e2e/`.

## Decisiones arquitectónicas

- Toda decisión arquitectónica relevante se documenta como ADR en `docs/decisions/`.
- Los ADR no se modifican después de ser aprobados (se crean nuevos si la decisión cambia).
- El formato de nombre es: `ADR-NNN-slug-descriptivo.md`.

## Convenciones generales

- La documentación del proyecto es en español.
- Los archivos de documentación usan formato Markdown.
- Cada directorio tiene un propósito único y no se mezclan responsabilidades.
- No crear archivos fuera de la estructura definida sin justificación.
