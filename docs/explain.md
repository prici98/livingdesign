# Effet des index — mesures EXPLAIN ANALYZE

Généré le 20/11/2026 à 18:10 par `db/postgres/explain/run_explain.py`. Temps = médiane de 5 exécutions.

Volume mesuré : `orders.orders` 20 000 lignes, `orders.order_items` 35 172 lignes, `inventory.stock` 15 425 lignes.

| Requête | Onglet | Sans index | Avec index | Gain |
| --- | --- | --- | --- | --- |
| Les 20 dernières commandes d'un client | Commandes | 1.117 ms — Seq Scan | 0.056 ms — Bitmap Index Scan (idx_orders_customer) | × 20 |
| Les 50 derniers paiements en échec | Commandes | 1.559 ms — Seq Scan | 0.105 ms — Index Scan (idx_orders_status_created) | × 15 |
| Quantité vendue d'un produit | Vue d'ensemble (meilleures ventes) | 1.788 ms — Seq Scan | 0.078 ms — Bitmap Index Scan (idx_order_items_product) | × 23 |
| Stock d'un produit dans tous les entrepôts | Catalogue / Logistique | 0.034 ms — Index Scan (stock_pkey) | 0.033 ms — Index Scan (idx_stock_product) | aucun : un autre index suffit déjà |

## Plans complets

### Les 20 dernières commandes d'un client

Index testé : `orders.idx_orders_customer`

```sql
SELECT id, status, total_cents, created_at FROM orders.orders WHERE customer_id = 42 ORDER BY created_at DESC LIMIT 20
```

**Sans index**

```
Limit  (cost=398.01..398.01 rows=2 width=25) (actual time=0.907..0.908 rows=2 loops=1)
  Buffers: shared hit=148
  ->  Sort  (cost=398.01..398.01 rows=2 width=25) (actual time=0.905..0.906 rows=2 loops=1)
        Sort Key: created_at DESC
        Sort Method: quicksort  Memory: 25kB
        Buffers: shared hit=148
        ->  Seq Scan on orders  (cost=0.00..398.00 rows=2 width=25) (actual time=0.782..0.897 rows=2 loops=1)
              Filter: (customer_id = 42)
              Rows Removed by Filter: 19998
              Buffers: shared hit=148
Planning Time: 0.100 ms
Execution Time: 0.931 ms
```

**Avec index**

```
Limit  (cost=11.64..11.65 rows=2 width=25) (actual time=0.027..0.028 rows=2 loops=1)
  Buffers: shared hit=4
  ->  Sort  (cost=11.64..11.65 rows=2 width=25) (actual time=0.026..0.026 rows=2 loops=1)
        Sort Key: created_at DESC
        Sort Method: quicksort  Memory: 25kB
        Buffers: shared hit=4
        ->  Bitmap Heap Scan on orders  (cost=4.30..11.63 rows=2 width=25) (actual time=0.018..0.020 rows=2 loops=1)
              Recheck Cond: (customer_id = 42)
              Heap Blocks: exact=2
              Buffers: shared hit=4
              ->  Bitmap Index Scan on idx_orders_customer  (cost=0.00..4.30 rows=2 width=0) (actual time=0.012..0.013 rows=2 loops=1)
                    Index Cond: (customer_id = 42)
                    Buffers: shared hit=2
Planning Time: 0.080 ms
Execution Time: 0.043 ms
```

### Les 50 derniers paiements en échec

Index testé : `orders.idx_orders_status_created`

```sql
SELECT id, customer_id, total_cents, created_at FROM orders.orders WHERE status = 'PAYMENT_FAILED' ORDER BY created_at DESC LIMIT 50
```

**Sans index**

```
Limit  (cost=412.15..412.28 rows=50 width=20) (actual time=1.343..1.348 rows=50 loops=1)
  Buffers: shared hit=148
  ->  Sort  (cost=412.15..413.22 rows=426 width=20) (actual time=1.340..1.342 rows=50 loops=1)
        Sort Key: created_at DESC
        Sort Method: top-N heapsort  Memory: 31kB
        Buffers: shared hit=148
        ->  Seq Scan on orders  (cost=0.00..398.00 rows=426 width=20) (actual time=0.013..1.269 rows=426 loops=1)
              Filter: (status = 'PAYMENT_FAILED'::text)
              Rows Removed by Filter: 19574
              Buffers: shared hit=148
Planning Time: 0.102 ms
Execution Time: 1.371 ms
```

**Avec index**

```
Limit  (cost=0.29..50.87 rows=50 width=20) (actual time=0.025..0.078 rows=50 loops=1)
  Buffers: shared hit=52
  ->  Index Scan using idx_orders_status_created on orders  (cost=0.29..431.27 rows=426 width=20) (actual time=0.025..0.074 rows=50 loops=1)
        Index Cond: (status = 'PAYMENT_FAILED'::text)
        Buffers: shared hit=52
Planning Time: 0.080 ms
Execution Time: 0.092 ms
```

### Quantité vendue d'un produit

Index testé : `orders.idx_order_items_product`

```sql
SELECT sum(quantity) AS sold FROM orders.order_items WHERE product_id = 123
```

**Sans index**

```
Aggregate  (cost=664.66..664.67 rows=1 width=8) (actual time=2.043..2.045 rows=1 loops=1)
  Buffers: shared hit=225
  ->  Seq Scan on order_items  (cost=0.00..664.65 rows=5 width=4) (actual time=0.023..2.035 rows=4 loops=1)
        Filter: (product_id = 123)
        Rows Removed by Filter: 35168
        Buffers: shared hit=225
Planning Time: 0.173 ms
Execution Time: 2.098 ms
```

**Avec index**

```
Aggregate  (cost=22.17..22.18 rows=1 width=8) (actual time=0.034..0.034 rows=1 loops=1)
  Buffers: shared hit=6
  ->  Bitmap Heap Scan on order_items  (cost=4.33..22.16 rows=5 width=4) (actual time=0.022..0.029 rows=4 loops=1)
        Recheck Cond: (product_id = 123)
        Heap Blocks: exact=4
        Buffers: shared hit=6
        ->  Bitmap Index Scan on idx_order_items_product  (cost=0.00..4.33 rows=5 width=0) (actual time=0.017..0.017 rows=4 loops=1)
              Index Cond: (product_id = 123)
              Buffers: shared hit=2
Planning Time: 0.091 ms
Execution Time: 0.058 ms
```

### Stock d'un produit dans tous les entrepôts

Index testé : `inventory.idx_stock_product`

```sql
SELECT warehouse_id, quantity, reserved FROM inventory.stock WHERE product_id = 123
```

**Sans index**

```
Index Scan using stock_pkey on stock  (cost=0.29..11.84 rows=3 width=12) (actual time=0.010..0.012 rows=3 loops=1)
  Index Cond: (product_id = 123)
  Buffers: shared hit=3
Planning Time: 0.116 ms
Execution Time: 0.025 ms
```

**Avec index**

```
Index Scan using idx_stock_product on stock  (cost=0.29..8.34 rows=3 width=12) (actual time=0.017..0.018 rows=3 loops=1)
  Index Cond: (product_id = 123)
  Buffers: shared hit=3
Planning Time: 0.067 ms
Execution Time: 0.031 ms
```
