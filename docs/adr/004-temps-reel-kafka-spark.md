# ADR-004 — Temps réel : Kafka et Spark Structured Streaming
**Statut** : acceptée

## Contexte
Le volet 4 demande de traiter un flux d'événements (clics, commandes, stock) en temps réel, avec des fenêtres de temps,
une tolérance aux retards, une reprise sans perte ni doublon après une panne, et une alerte visible au tableau de bord.
Cas d'usage retenu : la **logistique** (rupture de stock proche), complété par le suivi des commandes et un pic de commandes.

## Options étudiées
| Option | Points forts | Points faibles |
|---|---|---|
| **Kafka + Spark Structured Streaming** | Même outil que le lakehouse (Spark), fenêtres et watermark intégrés, checkpoint | Micro-lots : latence de l'ordre de la seconde, pas de la milliseconde |
| Kafka + Flink | Vraie faible latence, état très riche | Un outil de plus à apprendre et à opérer |
| Kafka Streams | Léger, intégré à Kafka | Java uniquement, pas réutilisable pour le lake |
| RabbitMQ | Simple | Pas de relecture de l'historique, pas fait pour le streaming analytique |

## Décision
Kafka (mode KRaft, 1 nœud) et Spark Structured Streaming 3.5, déclenchement toutes les 2 secondes.
- Topics : `clickstream` (clé `session_id`), `orders` (clé `order_id`), `stock` (clé `warehouse_id`), `alerts` ; 3 partitions chacun.
- Fenêtres fixes d'une minute, watermark de 2 minutes, mode `update` pour que le tableau de bord voie la minute en cours.
- **Exactly-once de bout en bout** obtenu par : relecture garantie (offsets Kafka dans le checkpoint) + écritures idempotentes
  dans PostgreSQL (`ON CONFLICT` sur une clé déterministe) + déduplication par `event_id`.
- L'alerte de rupture est calculée à partir des événements `stock-updated` publiés par le service inventory : le job ne lit
  jamais la base d'un autre service.

## Conséquences
- (+) Une alerte est détectée en quelques secondes ; le délai est mesuré par la vue `analytics.alert_latency`.
- (+) Arrêter puis relancer le job ne perd ni ne double aucun événement (démonstration dans `data-platform/streaming/README.md`).
- (−) Latence d'environ 2 secondes (taille d'un micro-lot) : suffisant pour la logistique, pas pour de la détection de fraude à la milliseconde.
- (−) Kafka sur un seul nœud, sans réplication : acceptable pour la démonstration, 3 nœuds en production.
- Tant que les services orders et inventory ne publient pas leurs événements, `producer.py` les simule au même format.
