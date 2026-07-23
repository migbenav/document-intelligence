# Problem Discovery

> Version: 0.1

---

# Pregunta

¿Qué problema estamos resolviendo y por qué vale la pena resolverlo?

---

# Problema

Los documentos complejos suelen contener conocimiento crítico sobre procesos, reglas, decisiones, políticas o especificaciones. Sin embargo, ese conocimiento permanece representado únicamente como texto.

A medida que los documentos evolucionan aparecen inconsistencias, duplicidad de información, contradicciones y conocimiento desactualizado, dificultando su mantenimiento y reduciendo la confianza en la documentación.

El problema aumenta cuando existen múltiples documentos relacionados, ya que un cambio realizado en uno de ellos puede requerir modificaciones en otros sin que exista una forma sencilla de identificar ese impacto.

---

# ¿Quién sufre este problema?

- Product Managers
- Business Analysts
- Software Architects
- Equipos de documentación
- Equipos legales
- Organizaciones con una gran cantidad de documentación

Especialmente cuando varias personas generan y mantienen documentación durante largos períodos de tiempo.

---

# ¿Cómo se resuelve actualmente?

Las organizaciones utilizan herramientas de documentación tradicionales como editores de texto, wikis o plataformas colaborativas.

Más recientemente han incorporado asistentes de IA que ayudan a redactar contenido o responder preguntas sobre documentos.

Sin embargo, estas herramientas siguen tratando el documento principalmente como texto y no como conocimiento estructurado.

---

# Limitaciones de las soluciones actuales

Las herramientas existentes suelen presentar una o más de las siguientes limitaciones:

- No representan explícitamente el conocimiento contenido en los documentos.
- No detectan automáticamente contradicciones entre documentos relacionados.
- No identifican el impacto que produce un cambio.
- No ayudan a mantener la consistencia a lo largo del tiempo.
- Se enfocan en generar texto, no en gestionar conocimiento.

---

# Oportunidad

Existe la oportunidad de construir una plataforma que transforme documentos en conocimiento estructurado.

En lugar de limitarse a generar texto, el sistema comprenderá el propósito, los conceptos, las relaciones, las reglas y las dependencias presentes en los documentos para asistir al usuario durante todo su ciclo de vida.

---

# Hipótesis

Si representamos el conocimiento contenido en un documento mediante un modelo estructurado y utilizamos IA para analizarlo, los usuarios podrán:

- comprender documentos complejos más rápidamente;
- detectar inconsistencias antes de que generen problemas;
- evaluar el impacto de cambios;
- mantener documentación más consistente y reutilizable.

---

# Criterio de validación

La hipótesis se considerará validada si el MVP demuestra que un usuario puede comprender, analizar y mantener un documento complejo con menor esfuerzo que utilizando únicamente un editor tradicional o un asistente de IA basado exclusivamente en texto.