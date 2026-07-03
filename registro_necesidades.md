# Registro de Necesidades - Proyecto Inversiones 📋

Este documento registra los requisitos definidos y por definir para el sistema de recomendación de inversiones.

---

## ── REQUISITOS GENERALES Y ARQUITECTURA ──

*   **Objetivo:** Desarrollar el sistema más rápido, estable y escalable.
*   **Decisión Técnica:** 
    *   **Backend:** Python + FastAPI (procesamiento numérico rápido, APIs robustas y asincronía).
    *   **Frontend:** React (Vite) + Vanilla CSS (alta velocidad de carga, diseño moderno a medida libre de pesos muertos de frameworks pesados).
*   **Alcance:** Encontrar las **Top 10 alternativas de inversión** en:
    1.  Mercado Argentino (Merval, CEDEARs, Letras, Bonos).
    2.  S&P 500.
    3.  Criptomonedas de mayor capitalización.

---

## ── PERFIL DE INVERSIÓN Y PARÁMETROS ──

*   **Horizonte de inversión:** Mediano plazo (**6 meses a 1 año** como máximo).
    *   *Impacto técnico:* Los indicadores técnicos y rankings darán prioridad a análisis semanales/diarios de mediano plazo (ej. cruce de EMAs de 50 y 200 días, momentum de medio término y rendimiento esperado de renta fija con vencimiento o duración media bajo ese rango de 6 a 12 meses).

---

## ── ASPECTOS CLAVE POR CLARIFICAR (Preguntas para afinar el sistema) ──

Para estructurar el backend y el frontend con la máxima precisión, te sugiero considerar las siguientes preguntas:

*   **Moneda de análisis:** Cada activo se mostrará en su **moneda original** (ARS para locales, USD para internacionales y cripto).
*   **Perfiles de Riesgo:** El sistema calculará y presentará un **Top 10 para cada perfil**:
    *   *Conservador:* Enfoque en Letras, Bonos estables y CEDEARs/Acciones de baja volatilidad.
    *   *Moderado:* Mix de renta variable de crecimiento, bonos medios y criptomonedas consolidadas.
    *   *Agresivo:* Alta participación de cripto, acciones de crecimiento y renta variable/bonos de alta volatilidad.
*   **Frecuencia de actualización:** Los datos se actualizarán de forma automática **una vez al día a las 11:00 AM** (coincidiendo con las aperturas y primeros datos estables del mercado).
*   **Categorización:** Separación explícita por categorías:
    1.  Merval (Acciones líderes locales)
    2.  CEDEARs
    3.  S&P 500
    4.  Letras (LECAPs/Boncer de corto plazo)
    5.  Bonos (Soberanos y Subsoberanos Argentinos)
    6.  Criptomonedas (Top cap)
*   **Restricción de Montos:** No hay límites ni referencias a montos. La plataforma entrega únicamente la recomendación óptima. La ejecución la realiza el usuario en su broker.
