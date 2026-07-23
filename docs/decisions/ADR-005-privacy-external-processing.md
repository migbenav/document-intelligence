# ADR-005 — Privacy and External Processing Constraints

> Estado: **Approved**
> Fecha: 2026-07-23
> Aprobada: 2026-07-23
> Depende de: ADR-001-mvp-scope.md, ADR-002-knowledge-model.md, ADR-003-document-ingestion.md, ADR-004-reliability-trust-model.md

---

# Contexto

Las ADRs anteriores han definido el alcance del MVP, el modelo de conocimiento, las restricciones de ingesta y el modelo de confianza. Todas estas decisiones asumen que un LLM procesa el contenido del documento, pero no se ha definido dónde ocurre ese procesamiento ni qué implicaciones de privacidad tiene.

**OBS-16 — No existen requisitos de privacidad o restricciones sobre envío de documentos a APIs externas de LLM**

Los documentos que procesa Document Intelligence pueden contener información sensible: estrategias de producto, requisitos de negocio, políticas internas, especificaciones técnicas confidenciales o incluso datos regulados. Enviar este contenido a un proveedor de IA externo implica que un tercero tiene acceso al texto completo del documento.

Para organizaciones con políticas de data governance o en dominios regulados, esta circunstancia puede ser inaceptable. La decisión de dónde se procesa el documento cambia fundamentalmente la arquitectura del sistema.

ADR-004 ya estableció que el sistema usa parámetros de generación controlados y tracking fijo de versión del modelo, pero no define si ese modelo es un servicio externo o un modelo alojado localmente.

---

# Principios de privacidad

Esta decisión se guía por los siguientes principios:

1. **Transparencia:** El usuario debe saber qué datos se procesan, dónde y por quién, antes de que ocurra el procesamiento.
2. **Consentimiento:** El usuario autoriza explícitamente el procesamiento de su documento. Sin consentimiento, no hay análisis.
3. **Minimización:** Solo se envía al proveedor de IA la información estrictamente necesaria para el análisis. No se envía metadata del usuario, historial ni información ajena al documento.
4. **Retención limitada:** El contenido del documento no se retiene más allá de lo operativamente necesario para completar el análisis y entregar los resultados al usuario.
5. **Abstracción del proveedor:** La arquitectura no debe acoplarse a un proveedor de IA específico, permitiendo cambiar el backend de procesamiento sin alterar el pipeline de análisis.

---

# Problema

¿Qué restricciones de privacidad aplican al procesamiento de documentos y dónde se ejecuta el modelo de IA que genera el Knowledge Model?

Específicamente:

1. ¿Los documentos del usuario se envían a servicios externos de IA?
2. ¿Qué nivel de transparencia se ofrece al usuario sobre el procesamiento de sus datos?
3. ¿Es necesario soportar procesamiento local o self-hosted desde el MVP?
4. ¿Qué garantías de privacidad ofrece el sistema?
5. ¿Cómo afecta esta decisión a la arquitectura del pipeline de análisis?

---

# Alternativas consideradas

---

## Alternativa 1 — Procesamiento externo con transparencia y consentimiento informado

**Descripción**

El MVP utiliza proveedores externos de IA para el análisis de documentos. El sistema es transparente con el usuario: antes de procesar un documento, informa explícitamente que el contenido será enviado a un servicio externo. El usuario debe dar consentimiento para proceder.

Componentes:

- El pipeline de análisis envía el contenido textual del documento a un servicio externo de IA.
- La UI informa al usuario qué tipo de procesamiento ocurrirá antes del análisis.
- El usuario acepta explícitamente el procesamiento externo.
- El contenido del documento no se retiene más allá de lo necesario para completar el análisis.
- Se documenta qué datos se envían y bajo qué condiciones.

**Ventajas**

- Simplicidad máxima de implementación: no se necesita infraestructura propia de inferencia.
- Acceso a modelos altamente capaces sin inversión en hardware.
- Menor costo operativo inicial: pago por uso.
- Permite iterar rápidamente sobre la calidad del análisis cambiando de modelo o proveedor.
- El consentimiento informado es una práctica estándar y suficiente para muchos contextos.

**Desventajas**

- Excluye usuarios y organizaciones con políticas que prohíben enviar documentos a terceros.
- Dependencia de disponibilidad, pricing y políticas del proveedor externo.
- Riesgo reputacional si un usuario envía información sensible sin comprender las implicaciones.
- No se puede garantizar completamente qué ocurre con los datos una vez enviados al proveedor.

**Impacto en MVP scope**

Bajo. Solo requiere un componente de consentimiento informado en la UI y documentación sobre privacidad.

**Impacto en arquitectura**

Bajo. El pipeline de análisis se diseña como un cliente que consume un servicio de IA externo.

**Escalabilidad futura**

Media. Si la demanda de procesamiento local crece, requiere agregar soporte para modelos self-hosted como un segundo adaptador. Sin abstracción explícita del proveedor, esto puede requerir refactoring.

---

## Alternativa 2 — Procesamiento local obligatorio

**Descripción**

El MVP ejecuta el modelo de IA localmente o en infraestructura controlada por el usuario. Los documentos nunca salen del entorno del usuario. Se utilizan modelos open-source que pueden ejecutarse sin conexión a internet.

Componentes:

- El pipeline de análisis ejecuta un modelo local.
- No existe comunicación con servicios externos de IA.
- El usuario es responsable de la infraestructura de inferencia.
- La privacidad está garantizada por diseño: los datos no abandonan el entorno controlado.

**Ventajas**

- Privacidad máxima: los documentos nunca salen del entorno del usuario.
- Sin dependencia de terceros.
- Atractivo para organizaciones reguladas y con políticas estrictas de data governance.
- Sin costos variables por llamada — el costo es la infraestructura fija.
- Total control sobre la versión del modelo.

**Desventajas**

- Los modelos disponibles localmente son actualmente menos capaces para tareas complejas de extracción estructurada, lo que pone en riesgo la validación de la hipótesis del producto.
- Requiere que el usuario tenga hardware capaz o un servidor dedicado.
- Mayor complejidad de setup para el usuario.
- Reduce significativamente la base de usuarios potenciales del MVP.
- Mayor dificultad para iterar sobre la calidad del análisis.

**Impacto en MVP scope**

Alto. Requiere seleccionar, evaluar y optimizar prompts para modelos con capacidades limitadas. Requiere documentar y facilitar el setup del runtime de inferencia.

**Impacto en arquitectura**

Alto. Necesita un runtime de inferencia local como dependencia del sistema y gestión de modelos descargados.

**Escalabilidad futura**

Media-baja. Si el producto necesita ofrecer una opción cloud en el futuro, requiere agregar integración con servicios externos. La arquitectura local-first es más compleja de extender hacia cloud que la inversa.

---

## Alternativa 3 — Procesamiento externo por defecto con arquitectura preparada para alternativas locales

**Descripción**

El MVP utiliza procesamiento externo de IA como opción por defecto (con transparencia y consentimiento), pero la arquitectura se diseña explícitamente con una capa de abstracción del proveedor de IA que permite reemplazar el procesamiento externo por modelos locales o self-hosted sin modificar el pipeline de análisis.

El MVP no implementa la opción local, pero garantiza que es viable agregarla sin reestructuración arquitectónica.

Componentes:

- Capa de abstracción del proveedor de IA que define las operaciones de análisis independientemente del backend de inferencia.
- Implementación por defecto: servicio externo de IA.
- Consentimiento informado antes del procesamiento.
- Documentación clara de qué datos se envían y bajo qué condiciones.
- La abstracción se diseña de forma que un adaptador local pueda implementarla sin cambios en el resto del sistema.
- El contenido del documento no se retiene más allá de lo operativamente necesario.

**Ventajas**

- Acceso inmediato a modelos altamente capaces para validar la hipótesis del producto.
- Simplicidad de implementación para el MVP.
- La abstracción del proveedor permite agregar opción local o self-hosted en el futuro sin reestructurar el pipeline.
- No compromete la arquitectura a un solo modelo de deployment.
- Transparencia con el usuario sobre el procesamiento de sus datos.
- Camino claro hacia soporte de procesamiento local cuando sea viable.

**Desventajas**

- En el MVP, los usuarios con restricciones estrictas de privacidad no pueden usar el sistema.
- El consentimiento informado no elimina la objeción fundamental de quienes no quieren que sus datos salgan de su entorno bajo ninguna circunstancia.
- La abstracción del proveedor agrega una capa de diseño que debe definirse correctamente desde el inicio.
- El soporte local futuro no tiene valor hasta que se implemente.

**Impacto en MVP scope**

Bajo-medio. Requiere diseñar la interfaz de abstracción del proveedor (no implementar múltiples backends) y el componente de consentimiento informado.

**Impacto en arquitectura**

Medio. La capa de abstracción del proveedor de IA debe diseñarse desde el inicio como contrato estable. Todas las llamadas al modelo pasan por esta capa. El pipeline de análisis no puede hacer asunciones sobre capacidades específicas del backend de inferencia.

**Escalabilidad futura**

Alta. Agregar un backend local o self-hosted es implementar un nuevo adaptador que cumple el contrato de la abstracción. El pipeline de análisis permanece intacto. El producto puede eventualmente ofrecer múltiples opciones de deployment.

---

# Consideraciones transversales

## Sobre los datos que se envían

Independientemente de la alternativa, el sistema debe documentar qué se envía al modelo de IA:

- El texto del documento (necesario para el análisis).
- Los prompts del sistema (instrucciones de extracción).
- Potencialmente el Knowledge Model parcial (si el análisis es multi-step).

No se envía: metadata del usuario, información de cuenta ni historial de uso previo.

## Sobre la retención de datos

"Retención limitada" no significa eliminación instantánea. El sistema puede mantener el contenido del documento en memoria o almacenamiento temporal durante el tiempo operativamente necesario para:

- completar el análisis (que puede ser multi-step);
- entregar los resultados al usuario;
- permitir que el usuario interactúe con el Knowledge Model durante su sesión.

Una vez que la sesión finaliza o el período de retención operativa expira, el contenido del documento original no se mantiene. El Knowledge Model generado (que es una representación derivada, no el documento completo) puede persistir según las necesidades de la funcionalidad.

## Sobre el RNF existente

El spec ya indica: "Debe ser posible reemplazar el proveedor del LLM sin modificar el resto del sistema." Este RNF es directamente compatible con esta decisión y se convierte en el principio arquitectónico que la habilita.

---

# Decisión final

**Decisión aprobada: Alternativa 3 — Procesamiento externo por defecto con arquitectura preparada para alternativas locales.**

## Resumen de la decisión

El MVP utiliza un proveedor externo de IA para el análisis de documentos. El sistema ofrece transparencia total y requiere consentimiento explícito del usuario. La arquitectura se diseña con una capa de abstracción del proveedor que permite, en iteraciones futuras, agregar opciones de procesamiento local o self-hosted sin modificar el pipeline de análisis.

## Requisitos del MVP

| Requisito | Prioridad |
|-----------|-----------|
| Informar al usuario que el documento será procesado por un servicio externo de IA | Must Have |
| Consentimiento explícito del usuario antes del análisis | Must Have |
| Documentar qué datos se envían y bajo qué condiciones | Must Have |
| Diseñar capa de abstracción del proveedor de IA como contrato estable | Must Have |
| Retención del contenido limitada a lo operativamente necesario | Must Have |
| Enviar solo la información mínima necesaria para el análisis | Must Have |
| Cifrado del documento en tránsito | Should Have |
| Opción de procesamiento local o self-hosted | Not Now |

## Fuera del alcance del MVP

- Procesamiento local o self-hosted.
- Selección de proveedor por parte del usuario.
- Cumplimiento de regulaciones específicas de industria (HIPAA, GDPR data residency, etc.).
- Auditoría detallada de acceso a datos.

## Documentos afectados

Una vez aplicada, los siguientes documentos deben actualizarse:

- `.specs/001-foundation/spec.md` — agregar requisitos de privacidad (consentimiento, transparencia, retención limitada), documentar la capa de abstracción del proveedor como principio de diseño, agregar restricciones de procesamiento.
- `docs/product/03-prd.md` — agregar sección de privacidad, actualizar fuera de alcance con procesamiento local.
