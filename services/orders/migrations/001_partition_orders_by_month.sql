-- =============================================================================
--  Migration 001 — partitionner orders.orders par mois
-- =============================================================================
--  Cahier des charges, volet 1 : « Découpez les très grosses tables en morceaux,
--  par exemple les commandes par date. »
--
--  Une table partitionnée est découpée en sous-tables, une par mois. Une requête
--  sur "les commandes de novembre" ne lit que la partition de novembre : c'est le
--  « partition pruning ». Et supprimer un vieux mois devient instantané (on
--  détache la partition au lieu d'effacer des milliers de lignes).
--
--  PostgreSQL ne sait pas transformer une table existante en table partitionnée.
--  La migration crée donc une nouvelle table, y copie les commandes, puis prend
--  la place de l'ancienne. Tout est exécuté dans UNE transaction par migrate.py :
--  si une étape échoue, rien n'est modifié.
--
--  Exécutée par le rôle orders_svc, propriétaire du schéma orders.
-- =============================================================================

SET search_path = orders;


-- -----------------------------------------------------------------------------
--  1. Les tables qui pointent vers orders gardent la date de leur commande
-- -----------------------------------------------------------------------------
--  Règle de PostgreSQL : la clé primaire d'une table partitionnée doit contenir
--  la colonne de découpage. La clé de orders devient donc (id, created_at), et
--  une clé étrangère vers orders doit désigner ces DEUX colonnes.
--  On ajoute order_created_at, on la remplit depuis orders, puis on la rend obligatoire.
ALTER TABLE order_items ADD COLUMN order_created_at timestamptz;
UPDATE order_items i SET order_created_at = o.created_at FROM orders o WHERE o.id = i.order_id;
ALTER TABLE order_items ALTER COLUMN order_created_at SET NOT NULL;

ALTER TABLE idempotency_keys ADD COLUMN order_created_at timestamptz;
UPDATE idempotency_keys k SET order_created_at = o.created_at FROM orders o WHERE o.id = k.order_id;
ALTER TABLE idempotency_keys ALTER COLUMN order_created_at SET NOT NULL;

-- Les anciennes clés étrangères (sur id seul) disparaissent : elles seront
-- recréées sur (id, created_at) à la fin.
ALTER TABLE order_items      DROP CONSTRAINT order_items_order_id_fkey;
ALTER TABLE idempotency_keys DROP CONSTRAINT idempotency_keys_order_id_fkey;


-- -----------------------------------------------------------------------------
--  2. La nouvelle table, partitionnée par plages de dates
-- -----------------------------------------------------------------------------
--  Mêmes colonnes et mêmes règles que l'ancienne. Elle réutilise le compteur
--  orders_id_seq : les numéros de commande continuent sans trou ni doublon.
CREATE TABLE orders_partitioned (
    id           INTEGER NOT NULL DEFAULT nextval('orders.orders_id_seq'),
    customer_id  INTEGER NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    status       TEXT NOT NULL CHECK (status IN ('PENDING', 'PAID', 'PREPARING', 'SHIPPED',
                                                 'DELIVERED', 'CANCELLED', 'PAYMENT_FAILED')),
    total_cents  INTEGER NOT NULL CHECK (total_cents >= 0),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);


-- -----------------------------------------------------------------------------
--  3. Une fonction qui crée la partition d'un mois
-- -----------------------------------------------------------------------------
--  Réutilisable plus tard, par exemple chaque mois par un job planifié.
--  PL/pgSQL est le langage de programmation intégré à PostgreSQL.
CREATE OR REPLACE FUNCTION create_month_partition(p_month date) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    v_start date := date_trunc('month', p_month)::date;                         -- 1er jour du mois
    v_end   date := (date_trunc('month', p_month) + interval '1 month')::date;  -- 1er jour du mois suivant
    v_name  text := format('orders_%s', to_char(v_start, 'YYYY_MM'));           -- ex. orders_2026_11
BEGIN
    -- %I insère un nom de table, %L une valeur, en les protégeant correctement.
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS orders.%I PARTITION OF orders.orders_partitioned '
        'FOR VALUES FROM (%L) TO (%L)',
        v_name, v_start, v_end);
END $$;

-- Une partition par mois, du mois de la plus ancienne commande jusqu'à 3 mois
-- dans le futur (pour que les prochaines commandes aient déjà leur place).
DO $$
DECLARE
    v_month date := date_trunc('month', COALESCE((SELECT min(created_at) FROM orders.orders), now()))::date;
BEGIN
    WHILE v_month <= date_trunc('month', now() + interval '3 months') LOOP
        PERFORM orders.create_month_partition(v_month);
        v_month := v_month + interval '1 month';
    END LOOP;
END $$;

-- Filet de sécurité : une commande hors de toutes les plages tombe ici au lieu d'échouer.
CREATE TABLE orders_default PARTITION OF orders_partitioned DEFAULT;


-- -----------------------------------------------------------------------------
--  4. Copier les commandes, puis prendre la place de l'ancienne table
-- -----------------------------------------------------------------------------
--  Chaque ligne tombe automatiquement dans la partition de son mois.
INSERT INTO orders_partitioned (id, customer_id, status, total_cents, created_at)
SELECT id, customer_id, status, total_cents, created_at FROM orders;

-- Le compteur appartenait à l'ancienne table : sans cette ligne, il serait
-- supprimé avec elle.
ALTER SEQUENCE orders_id_seq OWNED BY NONE;
DROP TABLE orders;

ALTER TABLE orders_partitioned RENAME TO orders;
ALTER SEQUENCE orders_id_seq OWNED BY orders.id;

-- On redonne aux contraintes les noms qu'elles avaient (les noms automatiques
-- ont été tirés de "orders_partitioned").
ALTER TABLE orders RENAME CONSTRAINT orders_partitioned_pkey             TO orders_pkey;
ALTER TABLE orders RENAME CONSTRAINT orders_partitioned_customer_id_fkey TO orders_customer_id_fkey;
ALTER TABLE orders RENAME CONSTRAINT orders_partitioned_status_check     TO orders_status_check;
ALTER TABLE orders RENAME CONSTRAINT orders_partitioned_total_cents_check TO orders_total_cents_check;


-- -----------------------------------------------------------------------------
--  5. Index et clés étrangères
-- -----------------------------------------------------------------------------
--  Un index créé sur la table mère est créé automatiquement sur chaque partition.
CREATE INDEX idx_orders_customer       ON orders (customer_id);
CREATE INDEX idx_orders_status_created ON orders (status, created_at DESC);

-- Les clés étrangères pointent maintenant vers (id, created_at).
ALTER TABLE order_items ADD CONSTRAINT order_items_order_fkey
    FOREIGN KEY (order_id, order_created_at) REFERENCES orders (id, created_at) ON DELETE CASCADE;
ALTER TABLE idempotency_keys ADD CONSTRAINT idempotency_keys_order_fkey
    FOREIGN KEY (order_id, order_created_at) REFERENCES orders (id, created_at) ON DELETE CASCADE;

-- Statistiques à jour pour que le planificateur fasse les bons choix.
ANALYZE orders;
