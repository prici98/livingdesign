# Partitionnement des commandes — mesure EXPLAIN

Généré par `db/postgres/explain/run_partition_explain.py`, lancé une fois avant et une fois après `services/orders/migrations/001_partition_orders_by_month.sql`.

Requête mesurée (onglet Vue d'ensemble : commandes et chiffre d'affaires du mois en cours) :

```sql
SELECT count(*) AS commandes, sum(total_cents) AS ca_cents FROM orders.orders WHERE created_at >= '2026-11-01' AND created_at < '2026-12-01'
```

<!-- avant -->
## Avant : table simple

Mesuré le 23/11/2026 à 22:40, médiane de 5 exécutions.

| Mesure | Valeur |
| --- | --- |
| Tables lues | 1 : `orders` |
| Lignes examinées | 20 000 sur 20 000 commandes |
| Blocs lus (8 Ko) | 148 |
| Temps d'exécution | 2.800 ms |

```
Aggregate  (cost=466.06..466.06 rows=1 width=16) (actual time=2.494..2.496 rows=1 loops=1)
  Buffers: shared hit=148
  ->  Seq Scan on orders  (cost=0.00..448.00 rows=3611 width=4) (actual time=0.012..2.202 rows=3578 loops=1)
        Filter: ((created_at >= '2026-11-01 00:00:00+00'::timestamp with time zone) AND (created_at < '2026-12-01 00:00:00+00'::timestamp with time zone))
        Rows Removed by Filter: 16422
        Buffers: shared hit=148
Planning Time: 0.104 ms
Execution Time: 2.528 ms
```
<!-- /avant -->

<!-- apres -->
## Après : table partitionnée par mois

Mesuré le 23/11/2026 à 22:44, médiane de 5 exécutions.

| Mesure | Valeur |
| --- | --- |
| Tables lues | 1 : `orders_2026_11` |
| Lignes examinées | 3 578 sur 20 000 commandes |
| Blocs lus (8 Ko) | 27 |
| Temps d'exécution | 1.195 ms |

```
Aggregate  (cost=98.55..98.56 rows=1 width=16) (actual time=0.891..0.892 rows=1 loops=1)
  Buffers: shared hit=27
  ->  Seq Scan on orders_2026_11 orders  (cost=0.00..80.67 rows=3577 width=4) (actual time=0.011..0.616 rows=3578 loops=1)
        Filter: ((created_at >= '2026-11-01 00:00:00+00'::timestamp with time zone) AND (created_at < '2026-12-01 00:00:00+00'::timestamp with time zone))
        Buffers: shared hit=27
Planning Time: 0.172 ms
Execution Time: 0.914 ms
```
<!-- /apres -->
