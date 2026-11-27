# contracts/events/ — format des messages Kafka

Écrits avant le code, comme les contrats d'API. Chaque message est un JSON validé par son schéma (JSON Schema 2020-12).

| Topic | Message | Clé de partition | Producteur | Consommateur |
|---|---|---|---|---|
| `livingdesign.clickstream` | `clickstream-event` | `session_id` | site (simulé par le producteur) | job Spark : vues par catégorie |
| `livingdesign.orders` | `order-created` | `order_id` | service orders (simulé en attendant) | job Spark : commandes et CA par minute, pic de commandes |
| `livingdesign.stock` | `stock-updated` | `warehouse_id` | service inventory (simulé en attendant) | job Spark : alerte de rupture |
| `livingdesign.alerts` | `alert` | `alert_id` | job Spark | tableau de bord |

Règles communes :
- `event_id` (UUID) unique : un consommateur qui reçoit deux fois le même message l'ignore.
- `occurred_at` en UTC, au format ISO 8601 : c'est le **temps de l'événement**, utilisé par les fenêtres et le watermark de Spark (pas l'heure d'arrivée dans Kafka).
- Montants en centimes entiers, comme dans les bases.
- Les messages d'une même clé arrivent dans l'ordre (ils vont dans la même partition).
