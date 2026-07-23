# Product Requirements Document

> Version: 0.2
> Decisiones aplicadas: ADR-001-mvp-scope.md, ADR-002-knowledge-model.md

---

# Objetivo

> Decisión documentada en: decisions/ADR-001-mvp-scope.md

Construir un MVP de una plataforma de inteligencia documental que permita transformar un documento complejo en un Knowledge Model (modelo de conocimiento estructurado) que pueda ser analizado y consultado mediante inteligencia artificial.

El MVP debe demostrar que un documento puede ser comprendido más allá de su contenido textual, identificando elementos relevantes, inconsistencias internas, información faltante y oportunidades de mejora.

---

# Usuario objetivo

Personas y equipos que trabajan con documentación compleja y necesitan crear, revisar o mantener conocimiento estructurado.

Ejemplos:

- Product Managers.
- Business Analysts.
- Software Architects.
- Equipos técnicos.
- Organizaciones con múltiples documentos relacionados.

---

# Caso de uso principal

Un usuario carga un documento complejo.

El sistema analiza su contenido y genera una representación estructurada que permite:

- entender el propósito del documento;
- identificar conceptos importantes;
- encontrar reglas y restricciones;
- detectar inconsistencias internas (contradicciones y ambigüedades);
- identificar información faltante según la estructura esperada;
- obtener sugerencias de mejora;
- consultar información mediante IA.

---

# Capacidades del MVP

## C1. Ingreso de documentos

El usuario puede proporcionar documentos para análisis.

Resultado esperado:

El sistema procesa el documento y genera un Knowledge Model: una representación interna estructurada con elementos tipados y relaciones opcionales entre ellos.

---

## C2. Comprensión documental

El sistema construye un Knowledge Model identificando los siguientes elementos (taxonomía fija en el MVP):

- propósito;
- conceptos;
- actores;
- reglas;
- procesos;
- restricciones.

Cada elemento incluye un tipo, contenido textual y referencia a su ubicación en el documento fuente. Las relaciones entre elementos se capturan de forma opcional cuando el sistema las identifica con suficiente confianza.

---

## C3. Exploración del conocimiento

El usuario puede visualizar y consultar el Knowledge Model generado.

Ejemplos:

- ¿Cuál es el objetivo de este documento?
- ¿Qué reglas define?
- ¿Quiénes participan?
- ¿Qué conceptos son importantes?
- ¿Qué relaciones existen entre los elementos?

---

## C4. Análisis de calidad documental

El sistema evalúa la calidad del documento basándose en el Knowledge Model generado:

- detecta inconsistencias internas: contradicciones y ambigüedades dentro del documento;
- identifica información faltante según la estructura esperada para el tipo de documento;
- genera sugerencias de mejora.

---

## C5. Asistencia mediante IA

El usuario puede interactuar con el Knowledge Model utilizando lenguaje natural.

---

# Fuera de alcance

El MVP no incluirá:

- Knowledge Graph completo (motor de grafos dedicado);
- análisis multi-documento ni relaciones entre documentos;
- configuración dinámica de taxonomías;
- detección de inconsistencias entre documentos relacionados;
- análisis de impacto de cambios entre documentos;
- edición colaborativa;
- control documental empresarial;
- gestión avanzada de permisos;
- flujos de aprobación;
- integración con sistemas externos;
- sincronización automática entre múltiples repositorios.

---

# Criterios de éxito

El MVP será exitoso si demuestra que:

- un usuario puede comprender un documento complejo más rápido;
- la IA puede explicar el contenido basado en conocimiento extraído;
- se pueden identificar inconsistencias internas que serían difíciles de encontrar manualmente;
- el sistema detecta información faltante relevante para el tipo de documento;
- las sugerencias de mejora aportan valor al usuario.

---

# Flujo principal del usuario

1. El usuario ingresa un documento.

2. El sistema analiza el contenido.

3. La IA identifica elementos relevantes:
   - propósito
   - conceptos
   - actores
   - reglas
   - procesos
   - restricciones

4. El sistema genera un Knowledge Model: elementos tipados con relaciones opcionales.

5. El sistema evalúa la calidad documental:
   - inconsistencias internas
   - información faltante según estructura esperada
   - sugerencias de mejora

6. El usuario puede explorar el conocimiento generado y los resultados del análisis de calidad.

7. El usuario puede realizar preguntas sobre el documento.

8. El sistema responde utilizando el conocimiento extraído.

---

# Prioridad del MVP

## Must Have

- Cargar documento.
- Analizar documento.
- Generar Knowledge Model (elementos tipados con relaciones opcionales).
- Detectar inconsistencias internas.
- Identificar información faltante según estructura esperada.
- Sugerir mejoras basadas en el Knowledge Model.
- Consultar mediante IA.
- Mostrar resultados.

## Should Have

- Mostrar relaciones internas entre conceptos del documento.
- Permitir feedback del usuario sobre los resultados.

## Could Have

- Taxonomía configurable por tipo de documento.
- Exportar conocimiento extraído.

## Not Now

- Knowledge Graph completo (motor de grafos dedicado).
- Configuración dinámica de taxonomías.
- Análisis multi-documento.
- Relaciones entre documentos.
- Comparar documentos.
- Analizar impacto de cambios entre documentos.
- Colaboración.
- Control de versiones.
- Integraciones externas.