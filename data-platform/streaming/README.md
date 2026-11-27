# data-platform/streaming/ — le temps réel (volet 4)

```
producteur (ton PC) ──► Kafka ──► job Spark Structured Streaming ──► PostgreSQL analytics ──► tableau de bord
                         3 topics        fenêtres, watermark,             orders_per_minute
                                         checkpoint, alertes              category_views_per_minute
                                                │                         alerts
                                                └──────► topic livingdesign.alerts
```

| Fichier | Rôle |
|---|---|
| `producer.py` | Simule clics, commandes et mises à jour de stock à partir du vrai catalogue et du vrai stock (contrats : `contracts/events/`) |
| `streaming_job.py` | Le job Spark : commandes et CA par minute, vues par catégorie, alertes LOW_STOCK et ORDER_SPIKE |
| `Dockerfile` | L'image du job (Spark 3.5.8 officiel + psycopg) |

## Démarrer

Une seule fois, sur une base qui existe déjà : ajouter `ANALYTICS_DB_PASSWORD` dans `infra/.env`, puis

```
docker compose -f infra/docker-compose.yml up -d
uv run python db/postgres/analytics/setup_analytics.py
```

Ensuite, à chaque fois :

```
docker compose -f infra/docker-compose.yml up -d                       # Kafka + job Spark (premier lancement : quelques minutes)
uv run python data-platform/streaming/producer.py --seconds 120        # envoie des événements
docker compose -f infra/docker-compose.yml logs -f spark-streaming     # ce que fait le job
```

Interface Spark : http://localhost:4040, onglet **Structured Streaming** (débit, durée des lots).

## Les démonstrations pour la soutenance

**1. Une alerte en quelques secondes.** Pendant que le producteur tourne :
```sql
SELECT alert_type, message, occurred_at, detected_at FROM analytics.alerts ORDER BY detected_at DESC LIMIT 5;
SELECT * FROM analytics.alert_latency;     -- délai moyen entre l'événement et sa détection
```

**2. Pic de commandes.** `uv run python data-platform/streaming/producer.py --spike` → une alerte ORDER_SPIKE.

**3. Watermark.** `uv run python data-platform/streaming/producer.py --late 0.2` : 20 % des événements arrivent avec 1 à 4 minutes de retard. Les logs du job affichent combien ont été ignorés (plus de 2 minutes de retard).

**4. Panne et reprise sans perte ni doublon (checkpoint).**
1. Lancer le producteur pour 3 minutes : `uv run python data-platform/streaming/producer.py --seconds 180`
2. Pendant qu'il tourne, arrêter le job : `docker compose -f infra/docker-compose.yml stop spark-streaming`
3. Attendre 30 secondes (Kafka garde les messages), puis : `docker compose -f infra/docker-compose.yml start spark-streaming`
4. Le job reprend où il s'était arrêté. Vérifier : le total des commandes de `analytics.orders_per_minute` est égal au nombre de commandes affiché par le producteur à la fin.

```sql
SELECT sum(orders) FROM analytics.orders_per_minute;
```

## Pourquoi pas de perte ni de doublon (exactly-once)

- **Pas de perte** : Spark note dans le checkpoint jusqu'où il a lu chaque partition Kafka. Un lot non terminé est relu au redémarrage.
- **Pas de doublon** : un lot relu réécrit les mêmes lignes (clé = début de fenêtre, ou `alert_id`), avec `ON CONFLICT` : le résultat ne change pas. Les commandes reçues deux fois sont écartées par `event_id`.
- **Côté producteur** : `enable.idempotence` empêche Kafka d'enregistrer deux fois un message renvoyé après une coupure.
- **Limite assumée** : le topic `livingdesign.alerts` peut recevoir deux fois la même alerte après une reprise. Les consommateurs l'ignorent grâce à `alert_id`.
