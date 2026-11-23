# Migrations du schéma orders

Une migration fait évoluer le schéma après sa création initiale (`db/postgres/init/`).
Fichiers numérotés `NNN_description.sql`, appliqués dans l'ordre par `migrate.py`, chacun dans une transaction.
Les migrations faites sont notées dans `orders.schema_migrations` : relancer le script ne refait rien.

```
uv run python services/orders/migrations/migrate.py
```

| Migration | Rôle |
|---|---|
| `001_partition_orders_by_month.sql` | Partitionne `orders.orders` par mois (volet 1). La clé devient `(id, created_at)` ; `order_items` et `idempotency_keys` reçoivent `order_created_at` pour leur clé étrangère. |

**Pour le service orders** : toute insertion dans `order_items` ou `idempotency_keys` doit fournir `order_created_at`,
la date de création de la commande (renvoyée par l'`INSERT … RETURNING id, created_at` de la commande).
