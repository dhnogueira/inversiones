# Proyecto Inversiones 📈

Este proyecto tiene como objetivo diseñar e implementar un sistema inteligente para identificar y clasificar las mejores alternativas de inversión en tres mercados clave:
1. **Mercado Argentino**: Acciones del panel líder (Merval), CEDEARs, Bonos soberanos/subsoberanos y Letras del Tesoro (LECAPs, etc.).
2. **S&P 500 (Mercado de EE.UU.)**: Acciones líderes analizadas bajo métricas de valuación, momentum y riesgo/retorno.
3. **Criptomonedas**: Activos digitales de alta capitalización analizados por volumen, tendencia y fuerza relativa.

---

## Estructura del Sistema (Propuesta)

La arquitectura recomendada para este sistema consiste en:

1. **Backend & Motor de Análisis (Python - FastAPI)**
   - **Extracción de datos**: Integración con Python APIs (como `yfinance` para S&P 500 y CEDEARs/Merval), scrapers o APIs públicas para Bonos/Letras argentinos, y la API de CoinGecko/Binance para criptomonedas.
   - **Algoritmo de Scoring**:
     - *Renta Variable (Equities / CEDEARs)*: Evaluador basado en Momentum (RSI, cruces de medias), Calidad/Valuación (P/E, P/B, EV/EBITDA) y Riesgo (Sharpe, Beta).
     - *Renta Fija (Bonos / Letras)*: Retorno esperado (TIR, TNA), ajuste por inflación/tipo de cambio (CER, Dollar Linked) y duración (sensibilidad a la tasa).
     - *Criptomonedas*: Tendencia (MACD, RSI), capitalización y consistencia de volumen a corto/mediano plazo.
   - **Exposición de datos**: API REST rápida y eficiente.

2. **Frontend Interactivo (React + Vite + Vanilla CSS)**
   - Interfaz con diseño premium en modo oscuro (estilo FinTech moderno, con gradientes suaves, efectos de vidrio/glassmorphism y micro-animaciones).
   - Paneles dedicados con tablas interactivas y ordenadas para el **Top 10** de cada categoría.
   - Gráficos interactivos de cotizaciones y distribución de activos (usando librerías ligeras como `Recharts` o `Chart.js`).
   - Panel de configuración para ajustar las ponderaciones/criterios del algoritmo de recomendación.
