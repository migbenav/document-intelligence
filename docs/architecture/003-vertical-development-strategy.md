# 003 — Estrategia de desarrollo vertical y revisión del orden de implementación

> Fecha: 2026-07-24
> Contexto: Post-completión de Feature 1 (Document Ingestion)
> Aplica a: Features 2-7 del MVP

---

## Cambio de estrategia

### Enfoque anterior (backend-first)

La Feature 1 se implementó siguiendo un enfoque de backend completo: todo el pipeline de ingesta (validación, extracción, persistencia, API) se desarrolló sin interfaz visual. Este enfoque fue razonable para la primera feature porque:

- La ingesta es puramente una capacidad de infraestructura.
- No requiere feedback visual del usuario para validarse (los tests son suficientes).
- Establece los cimientos sobre los que se construye todo lo demás.

### Nuevo enfoque (desarrollo vertical)

A partir de la segunda feature, cada incremento debe incluir, cuando sea razonable:

1. **Backend** — lógica de negocio y procesamiento.
2. **API** — endpoints que exponen la funcionalidad.
3. **Persistencia** — schema y storage necesarios.
4. **Integración** — conexión entre los componentes nuevos y los existentes.
5. **Interfaz mínima** — UI que permita demostrar y validar visualmente la funcionalidad.

### Razón del cambio

| Riesgo del enfoque backend-first | Mitigación con enfoque vertical |
|----------------------------------|--------------------------------|
| Llegar al final con un backend funcional pero sin forma de demostrar valor | Cada feature es demostrable individualmente |
| Descubrir problemas de UX solo al final, cuando el costo de cambio es alto | Problemas de UX se detectan tempranamente |
| Dificultad para validar con usuarios reales sin interfaz | Se puede validar incrementalmente desde Feature 2 |
| Acumulación de deuda de integración frontend-backend | La integración se resuelve feature por feature |
| Motivación del equipo baja sin resultados visibles | Cada incremento produce algo tangible |

### Principios operativos

- La interfaz puede ser simple y utilitaria; la prioridad es poder ejercitar la funcionalidad.
- No se busca diseño visual pulido sino feedback funcional.
- Cada feature debe poder desplegarse independientemente (Render + Vercel auto-deploy).
- Las features pendientes (4, 5, 6) que comparten dependencia de Feature 3 pueden paralelizarse si hay capacidad.

---

## Revisión del orden de implementación

### Orden propuesto (confirmado)

```
1. Feature 2 — Application Shell & Upload UI
2. Feature 3 — Analysis Engine (Knowledge Model Extraction)
3. Feature 4 — KM Visualization & Exploration
4. Feature 5 — Document Quality Analysis
5. Feature 6 — Natural Language Queries
6. Feature 7 — User Feedback (Should Have)
```

### Análisis de alternativas de secuencia

Se evaluaron tres variantes del orden:

#### Variante A: Feature 3 antes de Feature 2 (motor de análisis sin UI)

**Argumento a favor:** El motor de análisis es la pieza más compleja y de mayor riesgo técnico. Comenzar por él permite descubrir limitaciones del LLM antes.

**Problema:** ADR-005 requiere consentimiento explícito del usuario antes de enviar datos al LLM. Sin UI de consentimiento (Feature 2), no se puede cumplir este requisito ni siquiera para testing manual realista. Además, el enfoque vertical pierde sentido si la primera feature nueva es puramente backend.

**Decisión:** Rechazada. Feature 2 primero.

#### Variante B: Feature 5 (Quality Analysis) antes de Feature 4 (Visualization)

**Argumento a favor:** La detección de inconsistencias es el diferenciador del producto (ADR-001). Implementarla antes daría resultados de alto valor más pronto.

**Problema:** Sin una visualización del Knowledge Model (Feature 4), los resultados de calidad no tienen contexto. El usuario vería "Inconsistencia entre elemento X y elemento Y" sin poder explorar qué son X e Y. La experiencia sería confusa y poco validable.

**Decisión:** Rechazada. La visualización antes que el análisis de calidad proporciona el contexto necesario para que el análisis sea comprensible.

#### Variante C: Feature 6 (NL Queries) antes de Feature 5 (Quality Analysis)

**Argumento a favor:** Las consultas en lenguaje natural reutilizan la misma infraestructura LLM de Feature 3 y son más simples de implementar. Podrían entregarse más rápido.

**Análisis:** Ambas features dependen de Feature 3 y son independientes entre sí. El orden entre ellas es una decisión de priorización de valor, no de dependencia técnica. La detección de inconsistencias (Feature 5) es el diferenciador del MVP según ADR-001; las consultas NL son valiosas pero no exclusivas (cualquier chatbot puede responder preguntas sobre un documento).

**Decisión:** Mantener Feature 5 antes de Feature 6 porque el diferenciador del producto tiene prioridad sobre funcionalidad incremental.

---

### Justificación detallada del orden final

#### Feature 2 primero: Application Shell & Upload UI

**Por qué ahora:**
- Establece la infraestructura del frontend (React, Vite, Tailwind, shadcn/ui, Zustand) que todas las features posteriores necesitan.
- Implementa el flujo de consentimiento requerido por ADR-005 (prerrequisito para Feature 3).
- Permite verificar visualmente que la ingesta (Feature 1) funciona end-to-end.
- Entrega inmediata de valor tangible: el usuario puede subir un documento y ver su estado.

**Qué incluye verticalmente:**
- Frontend: scaffolding completo, pantalla de upload, indicador de progreso, pantalla de estado.
- Backend: potencialmente ajustes menores a la API de ingesta si la UX lo requiere (ej. websocket para progreso real-time — o simplemente polling con el endpoint existente).
- Integración: cliente HTTP configurado, CORS verificado, deploy funcional.

---

#### Feature 3 segunda: Analysis Engine

**Por qué ahora:**
- Es el corazón del producto. Sin Knowledge Model no hay nada que mostrar, analizar ni consultar.
- La infraestructura LLM (LiteLLM, prompts, abstracción del proveedor) se establece aquí y se reutiliza en Features 5 y 6.
- El UI de consentimiento (Feature 2) ya existe como prerrequisito.

**Qué incluye verticalmente:**
- Backend: LLM abstraction layer, prompts versionados, extraction service, type inference, evidence verification.
- API: POST /analyze, GET /{id}/knowledge-model, POST /{id}/confirm-type.
- Persistencia: tabla knowledge_elements, tabla analysis_sessions, relaciones.
- Frontend: selector de tipo de documento (inferencia + confirmación), indicador de progreso del análisis, vista básica de "análisis completado" con resumen.

**Riesgo técnico:** Alto. La calidad de la extracción depende de prompt engineering y del modelo. Requiere iteración.

---

#### Feature 4 tercera: Visualization

**Por qué ahora:**
- El Knowledge Model ya existe (Feature 3). Es el momento natural de hacerlo visible.
- Proporciona el contexto necesario para que Features 5 y 6 sean comprensibles cuando se implementen.
- Es la feature que transforma datos en valor percibido por el usuario.

**Qué incluye verticalmente:**
- Frontend: vista principal del Knowledge Model (elementos agrupados por tipo), panel de detalle (contenido + source_ref), vista de relaciones (graph simple o lista con enlaces).
- Backend: ninguna lógica nueva significativa (los datos ya están disponibles).
- Integración: navegación entre elementos, deep-linking a evidencia.

**Riesgo técnico:** Bajo-medio. Es principalmente frontend. La complejidad está en la UX de la vista de relaciones.

---

#### Feature 5 cuarta: Quality Analysis

**Por qué ahora:**
- Es el diferenciador principal del producto (ADR-001).
- El usuario ya puede ver el Knowledge Model (Feature 4), por lo que los resultados de calidad tendrán contexto.
- Reutiliza la infraestructura LLM de Feature 3.

**Qué incluye verticalmente:**
- Backend: quality analysis service, prompts para detección de contradicciones/ambigüedades, evaluación de completitud por tipo, generación de sugerencias.
- API: GET /{id}/quality-analysis (o incluido en el endpoint del Knowledge Model).
- Persistencia: resultados de calidad asociados a la sesión de análisis.
- Frontend: panel de calidad (inconsistencias, faltantes, sugerencias), vinculación con elementos del KM, evidencia trazable.

**Riesgo técnico:** Alto. La detección de inconsistencias por LLM es inherentemente imprecisa. Requiere calibración de prompts y definición clara de qué constituye una "inconsistencia".

---

#### Feature 6 quinta: Natural Language Queries

**Por qué ahora:**
- Todas las piezas necesarias existen: Knowledge Model, infraestructura LLM, UI de chat.
- Es la feature más "standalone" — puede construirse sin afectar las anteriores.
- Completa la experiencia interactiva del producto.

**Qué incluye verticalmente:**
- Backend: query service, prompt construction con KM como contexto, response parsing con source_ref.
- API: POST /{id}/query.
- Frontend: panel de chat/consulta, respuestas con evidencia, historial de conversación (opcional para MVP).

**Riesgo técnico:** Medio. La calidad de las respuestas depende del contexto proporcionado al LLM. El Knowledge Model ya provee estructura, lo que mejora la calidad sobre RAG con texto plano.

---

#### Feature 7 última: User Feedback (Should Have)

**Por qué al final:**
- Es Should Have, no Must Have.
- Su valor es diferido (datos para mejora futura).
- El esfuerzo es mínimo y puede absorberse en Feature 4 si hay oportunidad.

**Qué incluye verticalmente:**
- Backend: endpoint de feedback, tabla mínima.
- Frontend: botones en panel de detalle de elemento.
- No incluye re-procesamiento ni edición.

---

## Oportunidades de optimización identificadas

### 1. Fusionar Feature 7 en Feature 4

El feedback (botones "incorrecto" / "irrelevante") es un componente de UI que vive en el panel de detalle del Knowledge Model. Si Feature 4 está bien diseñada, agregar los botones es trivial. El endpoint backend es mínimo.

**Recomendación:** Implementar Feature 7 como parte de Feature 4. Esto elimina una feature separada sin agregar complejidad significativa.

### 2. Paralelizar Features 4, 5 y 6

Las tres dependen de Feature 3 pero no entre sí. Si hay capacidad de desarrollo paralelo:
- Una pista trabaja en Feature 4 (frontend-heavy).
- Otra pista trabaja en Feature 5 (backend-heavy, prompts).
- Feature 6 se implementa al final o en paralelo con Feature 5.

**Recomendación:** Mantener el orden serial propuesto (es un proyecto de un desarrollador), pero tener en mente la posibilidad de paralelización si las circunstancias cambian.

### 3. Iteración temprana de prompts en Feature 3

El mayor riesgo técnico está en la calidad de extracción del Knowledge Model y la detección de inconsistencias. Ambos dependen de prompt engineering.

**Recomendación:** Durante Feature 3, dedicar tiempo explícito a iterar prompts con documentos reales antes de considerar la feature "completa". La visualización (Feature 4) puede usarse como herramienta de validación de la calidad del análisis.

---

## Resumen ejecutivo

| Criterio | Evaluación |
|----------|------------|
| ¿El orden respeta las dependencias técnicas? | ✅ Sí — Feature 2 antes de 3, Feature 3 antes de 4/5/6 |
| ¿El orden respeta los prerrequisitos de ADRs? | ✅ Sí — consentimiento (ADR-005) antes del LLM, tipo de documento (ADR-006) en Feature 3 |
| ¿El diferenciador del producto se implementa temprano? | ✅ Sí — Features 3+5 son el diferenciador, implementadas en posiciones 2 y 4 |
| ¿Cada incremento es demostrable? | ✅ Sí — cada feature produce algo visible y ejercitable |
| ¿Se minimiza el riesgo de integración tardía? | ✅ Sí — frontend y backend se desarrollan juntos desde Feature 2 |
| ¿El alcance del MVP se mantiene sin cambios? | ✅ Sí — ninguna feature se agrega ni elimina respecto al PRD |

**Conclusión:** El orden propuesto es adecuado para el enfoque vertical. No se identifican mejoras que justifiquen una reordenación, dado que las dependencias técnicas y los prerrequisitos de ADRs determinan la secuencia de forma natural. La única optimización recomendada es absorber Feature 7 dentro de Feature 4.
