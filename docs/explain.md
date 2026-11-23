# Effet des index — mesures EXPLAIN ANALYZE

Généré le 23/11/2026 à 22:45 par `db/postgres/explain/run_explain.py`. Temps = médiane de 5 exécutions.

Volume mesuré : `orders.orders` 20 000 lignes, `orders.order_items` 35 172 lignes, `inventory.stock` 15 425 lignes.

| Requête | Onglet | Sans index | Avec index | Gain |
| --- | --- | --- | --- | --- |
| Les 20 dernières commandes d'un client | Commandes | 2.491 ms — Seq Scan | 0.290 ms — Index Scan (orders_2026_05_customer_id_idx) | × 9 |
| Les 50 derniers paiements en échec | Commandes | 2.863 ms — Seq Scan | 0.347 ms — Index Scan (orders_2026_05_status_created_at_idx) | × 8 |
| Quantité vendue d'un produit | Vue d'ensemble (meilleures ventes) | 3.154 ms — Seq Scan | 0.071 ms — Bitmap Index Scan (idx_order_items_product) | × 44 |
| Stock d'un produit dans tous les entrepôts | Catalogue / Logistique | 0.036 ms — Index Scan (stock_pkey) | 0.046 ms — Index Scan (idx_stock_product) | aucun : un autre index suffit déjà |

## Plans complets

### Les 20 dernières commandes d'un client

Index testé : `orders.idx_orders_customer`

```sql
SELECT id, status, total_cents, created_at FROM orders.orders WHERE customer_id = 42 ORDER BY created_at DESC LIMIT 20
```

**Sans index**

```
Limit  (cost=401.25..401.27 rows=11 width=34) (actual time=2.039..2.043 rows=2 loops=1)
  Buffers: shared hit=151
  ->  Sort  (cost=401.25..401.27 rows=11 width=34) (actual time=2.036..2.040 rows=2 loops=1)
        Sort Key: orders.created_at DESC
        Sort Method: quicksort  Memory: 25kB
        Buffers: shared hit=151
        ->  Append  (cost=0.00..401.06 rows=11 width=34) (actual time=1.401..2.028 rows=2 loops=1)
              Buffers: shared hit=151
              ->  Seq Scan on orders_2026_05 orders_1  (cost=0.00..12.90 rows=1 width=26) (actual time=0.092..0.092 rows=0 loops=1)
                    Filter: (customer_id = 42)
                    Rows Removed by Filter: 632
                    Buffers: shared hit=5
              ->  Seq Scan on orders_2026_06 orders_2  (cost=0.00..54.93 rows=1 width=26) (actual time=0.307..0.307 rows=0 loops=1)
                    Filter: (customer_id = 42)
                    Rows Removed by Filter: 2714
                    Buffers: shared hit=21
              ->  Seq Scan on orders_2026_07 orders_3  (cost=0.00..55.90 rows=1 width=26) (actual time=0.309..0.309 rows=0 loops=1)
                    Filter: (customer_id = 42)
                    Rows Removed by Filter: 2792
                    Buffers: shared hit=21
              ->  Seq Scan on orders_2026_08 orders_4  (cost=0.00..61.74 rows=1 width=26) (actual time=0.478..0.478 rows=0 loops=1)
                    Filter: (customer_id = 42)
                    Rows Removed by Filter: 3099
                    Buffers: shared hit=23
              ->  Seq Scan on orders_2026_09 orders_5  (cost=0.00..64.24 rows=1 width=26) (actual time=0.212..0.244 rows=1 loops=1)
                    Filter: (customer_id = 42)
                    Rows Removed by Filter: 3218
                    Buffers: shared hit=24
              ->  Seq Scan on orders_2026_10 orders_6  (cost=0.00..79.58 rows=1 width=26) (actual time=0.305..0.305 rows=0 loops=1)
                    Filter: (customer_id = 42)
                    Rows Removed by Filter: 3966
                    Buffers: shared hit=30
              ->  Seq Scan on orders_2026_11 orders_7  (cost=0.00..71.72 rows=1 width=25) (actual time=0.259..0.273 rows=1 loops=1)
                    Filter: (customer_id = 42)
                    Rows Removed by Filter: 3577
                    Buffers: shared hit=27
              ->  Seq Scan on orders_2026_12 orders_8  (cost=0.00..0.00 rows=1 width=48) (actual time=0.003..0.003 rows=0 loops=1)
                    Filter: (customer_id = 42)
              ->  Seq Scan on orders_2027_01 orders_9  (cost=0.00..0.00 rows=1 width=48) (actual time=0.005..0.005 rows=0 loops=1)
                    Filter: (customer_id = 42)
              ->  Seq Scan on orders_2027_02 orders_10  (cost=0.00..0.00 rows=1 width=48) (actual time=0.002..0.002 rows=0 loops=1)
                    Filter: (customer_id = 42)
              ->  Seq Scan on orders_default orders_11  (cost=0.00..0.00 rows=1 width=48) (actual time=0.001..0.001 rows=0 loops=1)
                    Filter: (customer_id = 42)
Planning:
  Buffers: shared hit=8
Planning Time: 0.608 ms
Execution Time: 2.106 ms
```

**Avec index**

```
Limit  (cost=58.32..58.35 rows=11 width=34) (actual time=0.185..0.189 rows=2 loops=1)
  Buffers: shared hit=16
  ->  Sort  (cost=58.32..58.35 rows=11 width=34) (actual time=0.184..0.187 rows=2 loops=1)
        Sort Key: orders.created_at DESC
        Sort Method: quicksort  Memory: 25kB
        Buffers: shared hit=16
        ->  Append  (cost=0.28..58.13 rows=11 width=34) (actual time=0.058..0.175 rows=2 loops=1)
              Buffers: shared hit=16
              ->  Index Scan using orders_2026_05_customer_id_idx on orders_2026_05 orders_1  (cost=0.28..8.29 rows=1 width=26) (actual time=0.024..0.024 rows=0 loops=1)
                    Index Cond: (customer_id = 42)
                    Buffers: shared hit=2
              ->  Index Scan using orders_2026_06_customer_id_idx on orders_2026_06 orders_2  (cost=0.28..8.30 rows=1 width=26) (actual time=0.008..0.008 rows=0 loops=1)
                    Index Cond: (customer_id = 42)
                    Buffers: shared hit=2
              ->  Index Scan using orders_2026_07_customer_id_idx on orders_2026_07 orders_3  (cost=0.28..8.30 rows=1 width=26) (actual time=0.006..0.006 rows=0 loops=1)
                    Index Cond: (customer_id = 42)
                    Buffers: shared hit=2
              ->  Index Scan using orders_2026_08_customer_id_idx on orders_2026_08 orders_4  (cost=0.28..8.30 rows=1 width=26) (actual time=0.007..0.007 rows=0 loops=1)
                    Index Cond: (customer_id = 42)
                    Buffers: shared hit=2
              ->  Index Scan using orders_2026_09_customer_id_idx on orders_2026_09 orders_5  (cost=0.28..8.30 rows=1 width=26) (actual time=0.011..0.012 rows=1 loops=1)
                    Index Cond: (customer_id = 42)
                    Buffers: shared hit=3
              ->  Index Scan using orders_2026_10_customer_id_idx on orders_2026_10 orders_6  (cost=0.28..8.30 rows=1 width=26) (actual time=0.073..0.073 rows=0 loops=1)
                    Index Cond: (customer_id = 42)
                    Buffers: shared hit=2
              ->  Index Scan using orders_2026_11_customer_id_idx on orders_2026_11 orders_7  (cost=0.28..8.30 rows=1 width=25) (actual time=0.018..0.018 rows=1 loops=1)
                    Index Cond: (customer_id = 42)
                    Buffers: shared hit=3
              ->  Seq Scan on orders_2026_12 orders_8  (cost=0.00..0.00 rows=1 width=48) (actual time=0.009..0.009 rows=0 loops=1)
                    Filter: (customer_id = 42)
              ->  Seq Scan on orders_2027_01 orders_9  (cost=0.00..0.00 rows=1 width=48) (actual time=0.002..0.003 rows=0 loops=1)
                    Filter: (customer_id = 42)
              ->  Seq Scan on orders_2027_02 orders_10  (cost=0.00..0.00 rows=1 width=48) (actual time=0.006..0.006 rows=0 loops=1)
                    Filter: (customer_id = 42)
              ->  Seq Scan on orders_default orders_11  (cost=0.00..0.00 rows=1 width=48) (actual time=0.005..0.005 rows=0 loops=1)
                    Filter: (customer_id = 42)
Planning:
  Buffers: shared hit=12
Planning Time: 1.328 ms
Execution Time: 0.289 ms
```

### Les 50 derniers paiements en échec

Index testé : `orders.idx_orders_status_created`

```sql
SELECT id, customer_id, total_cents, created_at FROM orders.orders WHERE status = 'PAYMENT_FAILED' ORDER BY created_at DESC LIMIT 50
```

**Sans index**

```
Limit  (cost=417.43..417.56 rows=50 width=20) (actual time=2.768..2.781 rows=50 loops=1)
  Buffers: shared hit=151
  ->  Sort  (cost=417.43..418.51 rows=430 width=20) (actual time=2.765..2.772 rows=50 loops=1)
        Sort Key: orders.created_at DESC
        Sort Method: top-N heapsort  Memory: 32kB
        Buffers: shared hit=151
        ->  Append  (cost=0.00..403.15 rows=430 width=20) (actual time=0.020..2.611 rows=426 loops=1)
              Buffers: shared hit=151
              ->  Seq Scan on orders_2026_05 orders_1  (cost=0.00..12.90 rows=13 width=20) (actual time=0.020..0.089 rows=13 loops=1)
                    Filter: (status = 'PAYMENT_FAILED'::text)
                    Rows Removed by Filter: 619
                    Buffers: shared hit=5
              ->  Seq Scan on orders_2026_06 orders_2  (cost=0.00..54.93 rows=55 width=20) (actual time=0.008..0.327 rows=55 loops=1)
                    Filter: (status = 'PAYMENT_FAILED'::text)
                    Rows Removed by Filter: 2659
                    Buffers: shared hit=21
              ->  Seq Scan on orders_2026_07 orders_3  (cost=0.00..55.90 rows=47 width=20) (actual time=0.013..0.563 rows=47 loops=1)
                    Filter: (status = 'PAYMENT_FAILED'::text)
                    Rows Removed by Filter: 2745
                    Buffers: shared hit=21
              ->  Seq Scan on orders_2026_08 orders_4  (cost=0.00..61.74 rows=79 width=20) (actual time=0.019..0.425 rows=79 loops=1)
                    Filter: (status = 'PAYMENT_FAILED'::text)
                    Rows Removed by Filter: 3020
                    Buffers: shared hit=23
              ->  Seq Scan on orders_2026_09 orders_5  (cost=0.00..64.24 rows=62 width=20) (actual time=0.037..0.358 rows=62 loops=1)
                    Filter: (status = 'PAYMENT_FAILED'::text)
                    Rows Removed by Filter: 3157
                    Buffers: shared hit=24
              ->  Seq Scan on orders_2026_10 orders_6  (cost=0.00..79.58 rows=88 width=20) (actual time=0.010..0.414 rows=88 loops=1)
                    Filter: (status = 'PAYMENT_FAILED'::text)
                    Rows Removed by Filter: 3878
                    Buffers: shared hit=30
              ->  Seq Scan on orders_2026_11 orders_7  (cost=0.00..71.72 rows=82 width=20) (actual time=0.017..0.369 rows=82 loops=1)
                    Filter: (status = 'PAYMENT_FAILED'::text)
                    Rows Removed by Filter: 3496
                    Buffers: shared hit=27
              ->  Seq Scan on orders_2026_12 orders_8  (cost=0.00..0.00 rows=1 width=20) (actual time=0.003..0.003 rows=0 loops=1)
                    Filter: (status = 'PAYMENT_FAILED'::text)
              ->  Seq Scan on orders_2027_01 orders_9  (cost=0.00..0.00 rows=1 width=20) (actual time=0.006..0.006 rows=0 loops=1)
                    Filter: (status = 'PAYMENT_FAILED'::text)
              ->  Seq Scan on orders_2027_02 orders_10  (cost=0.00..0.00 rows=1 width=20) (actual time=0.002..0.002 rows=0 loops=1)
                    Filter: (status = 'PAYMENT_FAILED'::text)
              ->  Seq Scan on orders_default orders_11  (cost=0.00..0.00 rows=1 width=20) (actual time=0.002..0.002 rows=0 loops=1)
                    Filter: (status = 'PAYMENT_FAILED'::text)
Planning:
  Buffers: shared hit=8
Planning Time: 0.973 ms
Execution Time: 2.863 ms
```

**Avec index**

```
Limit  (cost=2.65..54.85 rows=50 width=20) (actual time=0.220..0.302 rows=50 loops=1)
  Buffers: shared hit=76
  ->  Merge Append  (cost=2.65..451.62 rows=430 width=20) (actual time=0.219..0.296 rows=50 loops=1)
        Sort Key: orders.created_at DESC
        Buffers: shared hit=76
        ->  Index Scan using orders_2026_05_status_created_at_idx on orders_2026_05 orders_1  (cost=0.28..16.46 rows=13 width=20) (actual time=0.064..0.065 rows=1 loops=1)
              Index Cond: (status = 'PAYMENT_FAILED'::text)
              Buffers: shared hit=3
        ->  Index Scan using orders_2026_06_status_created_at_idx on orders_2026_06 orders_2  (cost=0.28..51.26 rows=55 width=20) (actual time=0.012..0.012 rows=1 loops=1)
              Index Cond: (status = 'PAYMENT_FAILED'::text)
              Buffers: shared hit=3
        ->  Index Scan using orders_2026_07_status_created_at_idx on orders_2026_07 orders_3  (cost=0.28..50.66 rows=47 width=20) (actual time=0.008..0.008 rows=1 loops=1)
              Index Cond: (status = 'PAYMENT_FAILED'::text)
              Buffers: shared hit=3
        ->  Index Scan using orders_2026_08_status_created_at_idx on orders_2026_08 orders_4  (cost=0.28..56.93 rows=79 width=20) (actual time=0.007..0.007 rows=1 loops=1)
              Index Cond: (status = 'PAYMENT_FAILED'::text)
              Buffers: shared hit=3
        ->  Index Scan using orders_2026_09_status_created_at_idx on orders_2026_09 orders_5  (cost=0.28..56.53 rows=62 width=20) (actual time=0.009..0.009 rows=1 loops=1)
              Index Cond: (status = 'PAYMENT_FAILED'::text)
              Buffers: shared hit=3
        ->  Index Scan using orders_2026_10_status_created_at_idx on orders_2026_10 orders_6  (cost=0.28..69.26 rows=88 width=20) (actual time=0.042..0.042 rows=1 loops=1)
              Index Cond: (status = 'PAYMENT_FAILED'::text)
              Buffers: shared hit=3
        ->  Index Scan using orders_2026_11_status_created_at_idx on orders_2026_11 orders_7  (cost=0.28..108.17 rows=82 width=20) (actual time=0.016..0.085 rows=50 loops=1)
              Index Cond: (status = 'PAYMENT_FAILED'::text)
              Buffers: shared hit=50
        ->  Index Scan using orders_2026_12_status_created_at_idx on orders_2026_12 orders_8  (cost=0.12..8.14 rows=1 width=20) (actual time=0.007..0.007 rows=0 loops=1)
              Index Cond: (status = 'PAYMENT_FAILED'::text)
              Buffers: shared hit=2
        ->  Index Scan using orders_2027_01_status_created_at_idx on orders_2027_01 orders_9  (cost=0.12..8.14 rows=1 width=20) (actual time=0.006..0.006 rows=0 loops=1)
              Index Cond: (status = 'PAYMENT_FAILED'::text)
              Buffers: shared hit=2
        ->  Index Scan using orders_2027_02_status_created_at_idx on orders_2027_02 orders_10  (cost=0.12..8.14 rows=1 width=20) (actual time=0.030..0.030 rows=0 loops=1)
              Index Cond: (status = 'PAYMENT_FAILED'::text)
              Buffers: shared hit=2
        ->  Index Scan using orders_default_status_created_at_idx on orders_default orders_11  (cost=0.12..8.14 rows=1 width=20) (actual time=0.014..0.014 rows=0 loops=1)
              Index Cond: (status = 'PAYMENT_FAILED'::text)
              Buffers: shared hit=2
Planning:
  Buffers: shared hit=12
Planning Time: 0.777 ms
Execution Time: 0.354 ms
```

### Quantité vendue d'un produit

Index testé : `orders.idx_order_items_product`

```sql
SELECT sum(quantity) AS sold FROM orders.order_items WHERE product_id = 123
```

**Sans index**

```
Aggregate  (cost=922.66..922.67 rows=1 width=8) (actual time=3.592..3.594 rows=1 loops=1)
  Buffers: shared hit=483
  ->  Seq Scan on order_items  (cost=0.00..922.65 rows=5 width=4) (actual time=0.247..3.582 rows=4 loops=1)
        Filter: (product_id = 123)
        Rows Removed by Filter: 35168
        Buffers: shared hit=483
Planning Time: 0.222 ms
Execution Time: 3.656 ms
```

**Avec index**

```
Aggregate  (cost=22.88..22.89 rows=1 width=8) (actual time=0.029..0.030 rows=1 loops=1)
  Buffers: shared hit=6
  ->  Bitmap Heap Scan on order_items  (cost=4.33..22.87 rows=5 width=4) (actual time=0.018..0.025 rows=4 loops=1)
        Recheck Cond: (product_id = 123)
        Heap Blocks: exact=4
        Buffers: shared hit=6
        ->  Bitmap Index Scan on idx_order_items_product  (cost=0.00..4.33 rows=5 width=0) (actual time=0.013..0.013 rows=4 loops=1)
              Index Cond: (product_id = 123)
              Buffers: shared hit=2
Planning Time: 0.080 ms
Execution Time: 0.053 ms
```

### Stock d'un produit dans tous les entrepôts

Index testé : `inventory.idx_stock_product`

```sql
SELECT warehouse_id, quantity, reserved FROM inventory.stock WHERE product_id = 123
```

**Sans index**

```
Index Scan using stock_pkey on stock  (cost=0.29..11.84 rows=3 width=12) (actual time=0.009..0.011 rows=3 loops=1)
  Index Cond: (product_id = 123)
  Buffers: shared hit=3
Planning Time: 0.067 ms
Execution Time: 0.025 ms
```

**Avec index**

```
Index Scan using idx_stock_product on stock  (cost=0.29..8.34 rows=3 width=12) (actual time=0.019..0.021 rows=3 loops=1)
  Index Cond: (product_id = 123)
  Buffers: shared hit=3
Planning Time: 0.076 ms
Execution Time: 0.036 ms
```
