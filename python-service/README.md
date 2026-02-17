# VERGE AI Service

Microservicio de Inteligencia Artificial para el análisis de sentimiento de noticias de criptomonedas.

## Requisitos
- Python 3.8+
- pip

## Instalación
1. Crear un entorno virtual:
   ```bash
   python -m venv venv
   source venv/bin/activate  # En Windows: venv\Scripts\activate
   ```
2. Instalar dependencias:
   ```bash
   pip install -r requirements.txt
   ```

## Ejecución
```bash
python main.py
```
El servicio correrá en `http://localhost:8000`.

## Endpoints
- `GET /health`: Verifica el estado del servicio.
- `POST /analyze-sentiment`: Analiza el sentimiento de un texto.
  - Body: `{ "text": "Bitcoin is reaching new highs!" }`
  - Response: `{ "sentiment": "positive", "confidence": 0.98, ... }`
