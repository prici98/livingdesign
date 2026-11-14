# data-platform/ — la partie données
- `jobs-spark/` : traitements par lots. `ingest_dataset.py` nettoie le dataset IKEA (pandas pour l'instant, PySpark à l'étape Lakehouse)
- `streaming/`  : producteur Kafka et jobs Spark Structured Streaming (étape Streaming)
- `lakehouse/`  : zones raw / staging / curated / consumption, Delta Lake (étape Lakehouse)
- `data/`       : fichiers locaux, non versionnés. Mettre le dataset Kaggle dans `data/raw/`
