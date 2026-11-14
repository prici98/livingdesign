# infra/ — l'infrastructure, lancée avec Docker
- `docker-compose.yml` : PostgreSQL et MongoDB pour l'instant ; MinIO, Kafka et l'observabilité s'y ajouteront
- `.env.example` : modèle des variables ; copier en `.env` dans ce même dossier
- `minio/`, `kafka/`, `observability/` : configurations de chaque outil (étapes suivantes)
