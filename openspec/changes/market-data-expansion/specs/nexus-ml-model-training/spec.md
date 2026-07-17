## ADDED Requirements

### Requirement: Dataset de entrenamiento desde datos reales existentes
El sistema SHALL construir un dataset de entrenamiento para el modelo XGBoost de Nexus-15/Nexus-5 usando las 20 features ya definidas en `NEXUS15_FEATURES` (`python-service/nexus15/model_loader.py`) calculadas sobre klines históricos ya cacheados (`agent/data/klines.db`), etiquetado con el resultado real conocido (ej. retorno a N velas futuras, o resultado de TP/SL simulado).

#### Scenario: Símbolo con historia insuficiente para entrenar
- **WHEN** un símbolo tiene menos velas cacheadas que el mínimo requerido para generar ejemplos de entrenamiento válidos
- **THEN** se excluye del dataset de entrenamiento sin bloquear el proceso para el resto de los símbolos

### Requirement: Validación out-of-sample obligatoria
El modelo SHALL validarse con un split temporal (no aleatorio) — entrenar con un período histórico y validar con un período posterior nunca visto en entrenamiento — antes de considerarse apto para reemplazar el placeholder actual (`g6=0.5` fijo).

#### Scenario: Modelo con buen resultado en entrenamiento pero malo en validación
- **WHEN** el modelo muestra alta precisión sobre los datos de entrenamiento pero precisión cercana al azar en el período de validación posterior
- **THEN** el modelo NO se despliega — se documenta como sobreajuste (overfitting) y se descarta o se reintenta con más datos/regularización

### Requirement: Despliegue reemplaza el placeholder de forma auditable
El sistema SHALL desplegar el modelo entrenado como el archivo `.json` que `Nexus15ModelLoader`/`Nexus5ModelLoader` ya esperan (`models/nexus15/xgb_nexus15_v1.json`, `models/nexus5/xgb_nexus5_v1.json`), sin cambiar la interfaz de `predict()` existente, y registrar en el log cuándo el modelo real reemplaza al fallback de 0.5.

#### Scenario: Primer arranque con modelo real presente
- **WHEN** el archivo del modelo entrenado existe por primera vez en el path esperado
- **THEN** `Nexus15ModelLoader`/`Nexus5ModelLoader` lo cargan y loguean explícitamente "modelo real cargado" (en vez del warning actual de "fallback mode active")

### Requirement: Evaluación vía backtesting antes de producción
El sistema SHALL evaluar el impacto del modelo entrenado sobre cualquier StrategyProfile que dependa de Nexus-15/Nexus-5 usando el motor de backtesting existente, comparando resultados CON el modelo real vs. CON el placeholder de 0.5, antes de activarlo en perfiles en producción.

#### Scenario: El modelo real no mejora el resultado del placeholder
- **WHEN** el backtest muestra que el profit factor con el modelo real es igual o peor que con el placeholder de 0.5
- **THEN** no se despliega a producción — se documenta el resultado igual que se hizo con Caso 1/Caso 2/FVG
