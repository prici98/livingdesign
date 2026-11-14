# LivingDesign — plateforme e-commerce de mobilier et décoration

Plateforme data end-to-end : bases SQL/NoSQL, microservices et API, streaming temps réel, lakehouse.
Dataset de départ : produits IKEA (Kaggle).

## Organisation du dépôt (architecture validée)

```
livingdesign/
├── services/          les 5 microservices : orders, auth, inventory, payments, catalog
├── gateway/           API Gateway (NGINX)
├── contracts/         contrats OpenAPI, GraphQL et événements Kafka
├── libs/              code partagé (livingdesign_commons)
├── db/                création (init) et remplissage (seed) de PostgreSQL et MongoDB
├── data-platform/     jobs batch, streaming, lakehouse
├── infra/             docker-compose, MinIO, Kafka, observabilité
├── tests/             tests de bout en bout
├── docs/adr/          décisions d'architecture
├── ops/               sauvegardes, scripts d'exploitation, schémas d'architecture
└── .github/workflows/ intégration continue
```

Chaque dossier a son propre README qui explique son rôle.

## Démarrer (depuis la racine du projet)

Prérequis : [uv](https://docs.astral.sh/uv/) et Docker Desktop.

1. Mettre le dataset Kaggle dans `data-platform/data/raw/`.
2. Copier `infra/.env.example` en `infra/.env` et changer les mots de passe.
3. Lancer :

```
uv sync                                               # installe Python 3.12 et toutes les dépendances
uv run python data-platform/jobs-spark/ingest_dataset.py
docker compose -f infra/docker-compose.yml up -d
uv run python db/mongo/seed/load_catalog.py
uv run python db/postgres/seed/generate_fake_data.py
uv run pytest                                         # les tests
uv run ruff check .                                   # la qualité du code
```

Travail en binôme (branches, pull requests, dépendances) : voir [CONTRIBUTING.md](CONTRIBUTING.md).

## Feuille de route

| Étape | Contenu | État |
|---|---|---|
| 1 | Nettoyage du dataset (`data-platform/jobs-spark`) | ✅ |
| 2 | Bases PostgreSQL et MongoDB (`db/`, `infra/`) | ✅ |
| 3 | EXPLAIN, partitionnement (migration dans `services/orders/migrations`), sauvegarde / restauration (`ops/`) | |
| 4 | Contrats puis microservices (`contracts/`, `services/`) | |
| 5 | Gateway et authentification | |
| 6 | Kafka et Spark Streaming | |
| 7 | Lakehouse (MinIO, Delta) | |
| 8 | Observabilité, CI, soutenance | |
