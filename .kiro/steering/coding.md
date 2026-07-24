---
inclusion: auto
---

# Coding Conventions — Document Intelligence

## Language

- All source code must be written in English.
- Variables, functions, classes, modules, comments, and docstrings must use English.
- User-facing text must not be hardcoded. UI strings should be externalized to support future internationalization (i18n).

## Code Style

- Every public class and function should include a concise docstring describing its purpose, inputs, outputs, and possible exceptions.
- Comments should explain intent, business rules, or non-obvious implementation decisions.
- Prefer clear, self-explanatory code over excessive comments.
- Functions should have a single responsibility whenever practical.
- Prioritize readability and maintainability over brevity or premature optimization.

## Commenting Rules

- Comments must describe what the code does or why a particular approach was chosen, not the development history.
- Do not include comments that reference modifications, fixes, or implementation history (e.g., "updated", "fixed", "corrected", "new", "changed", "legacy", "temporary fix").
- Write comments as if the code were being read for the first time, independent of previous revisions.
- Historical context, implementation rationale, and change history belong in Git commits, pull requests, ADRs, or project documentation—not in the source code.

## Internationalization

- The application UI must be designed to support multiple languages.
- The application language is independent from the document language.
- User-visible strings should be stored in localization resources rather than embedded directly in the code.
