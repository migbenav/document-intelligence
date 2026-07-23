# Product Engineering Methodology (PEM)

Version: 1.0

---

# Objetivo

Definir una metodología reutilizable para diseñar, desarrollar y evolucionar productos de software utilizando IA como apoyo, sin depender de una herramienta específica.

El objetivo no es acelerar la generación de código, sino mejorar la calidad de las decisiones tomadas antes, durante y después del desarrollo.

---

# Filosofía

Todo producto es una sucesión de decisiones.

La calidad del producto dependerá más de la calidad de esas decisiones que de la velocidad con la que se escriba el código.

La metodología busca reducir incertidumbre de forma progresiva, documentando el razonamiento detrás de cada decisión.

---

# Principios

- Comprender el problema antes de diseñar la solución.
- Priorizar conocimiento sobre implementación.
- Reducir incertidumbre paso a paso.
- Un entregable verificable por etapa.
- Registrar las decisiones importantes.
- Diseñar primero el MVP.
- Evolucionar el producto de forma iterativa.
- Mantener independencia de herramientas específicas.

---

# Discovery Engine

El núcleo de la metodología es un proceso de descubrimiento adaptativo.

En lugar de seguir una lista rígida de preguntas, cada etapa identifica primero qué incertidumbre debe resolverse.

Las preguntas posteriores dependerán de:

- el tipo de proyecto;
- el dominio;
- las respuestas anteriores;
- las decisiones ya tomadas.

El objetivo no es responder muchas preguntas, sino responder únicamente aquellas que permitan tomar la siguiente decisión con mayor confianza.

---

# Flujo de trabajo

Cada etapa sigue el mismo ciclo:

1. Definir el objetivo.
2. Identificar la incertidumbre.
3. Formular las preguntas necesarias.
4. Analizar las respuestas.
5. Tomar decisiones.
6. Documentar conclusiones.
7. Generar especificaciones.
8. Implementar.
9. Validar.
10. Registrar el aprendizaje.

---

# Estructura de una etapa

Cada etapa debe incluir:

- Objetivo
- Preguntas de descubrimiento
- Conclusiones
- Decisiones tomadas
- Riesgos identificados
- Entregables generados
- Criterios de finalización

Una etapa no se considera finalizada hasta cumplir sus criterios de salida.

---

# Tipos de trabajo soportados

La metodología debe poder aplicarse a:

- Crear un producto nuevo.
- Agregar funcionalidades.
- Agregar módulos.
- Evolucionar un producto existente.
- Refactorizar arquitectura.
- Optimizar rendimiento.
- Analizar sistemas existentes.
- Migrar tecnologías.
- Preparar una nueva versión.

Cada flujo reutiliza los mismos principios, adaptando únicamente las preguntas de descubrimiento.

---

# Entregables

Dependiendo de la etapa, podrán generarse uno o varios de los siguientes artefactos:

- Documento de análisis.
- Product Vision.
- Domain Model.
- PRD.
- ADR (Architecture Decision Record).
- Arquitectura.
- Modelo de datos.
- APIs.
- UX.
- Roadmap.
- Specs.
- Tareas de implementación.
- Plan de pruebas.
- Plan de despliegue.

---

# Adaptadores

La metodología es independiente de cualquier herramienta.

Los entregables podrán transformarse posteriormente para ser utilizados por:

- Kiro
- Cursor
- Claude Code
- GitHub Copilot
- OpenAI Codex
- otras herramientas futuras.

Las herramientas implementan el proceso; no definen el proceso.

---

# Gestión del conocimiento

Toda decisión relevante deberá quedar registrada.

El conocimiento del proyecto forma parte del producto y debe evolucionar junto con el código.

La documentación oficial debe mantenerse sincronizada con la implementación.

---

# Objetivo final

Construir productos mantenibles, escalables y bien documentados mediante un proceso reproducible que facilite la colaboración, reduzca la incertidumbre y preserve el conocimiento generado durante todo el ciclo de vida del producto.