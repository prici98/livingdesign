
-- =============================================================================
--  1. Les rôles                                                             [+]
-- =============================================================================
--  [+] Cahier des charges : "un rôle PostgreSQL par service". Chaque service se
--      connecte avec son rôle et ne voit que son schéma.

-- \getenv copie une variable d'environnement (venue de infra/.env) dans une
-- variable psql : les mots de passe ne sont jamais écrits dans le dépôt.
\getenv orders_pw    ORDERS_DB_PASSWORD
\getenv inventory_pw INVENTORY_DB_PASSWORD
\getenv payments_pw  PAYMENTS_DB_PASSWORD
\getenv auth_pw      AUTH_DB_PASSWORD

-- CREATE ROLE … LOGIN = un utilisateur qui peut se connecter.
-- :'orders_pw' est remplacé par la valeur de la variable, entre apostrophes.
CREATE ROLE orders_svc    LOGIN PASSWORD :'orders_pw';
CREATE ROLE inventory_svc LOGIN PASSWORD :'inventory_pw';
CREATE ROLE payments_svc  LOGIN PASSWORD :'payments_pw';
CREATE ROLE auth_svc      LOGIN PASSWORD :'auth_pw';

-- Par défaut tout le monde (PUBLIC) peut se connecter à la base : on retire ce
-- droit, puis on le donne explicitement aux quatre rôles.
-- :"DBNAME" est remplacé par psql par le nom de la base courante.
REVOKE ALL ON DATABASE :"DBNAME" FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE :"DBNAME" TO orders_svc, inventory_svc, payments_svc, auth_svc;

-- search_path = le schéma utilisé quand on écrit "orders" au lieu de "orders.orders".
ALTER ROLE orders_svc    SET search_path = orders;
ALTER ROLE inventory_svc SET search_path = inventory;
ALTER ROLE payments_svc  SET search_path = payments;
ALTER ROLE auth_svc      SET search_path = auth;


-- =============================================================================
--  2. Les schémas : un par microservice
-- =============================================================================
--  [+] AUTHORIZATION = le propriétaire. Il a tous les droits sur son schéma ;
--      les autres rôles n'en ont aucun.
CREATE SCHEMA IF NOT EXISTS orders    AUTHORIZATION orders_svc;
CREATE SCHEMA IF NOT EXISTS inventory AUTHORIZATION inventory_svc;
CREATE SCHEMA IF NOT EXISTS payments  AUTHORIZATION payments_svc;
CREATE SCHEMA IF NOT EXISTS auth      AUTHORIZATION auth_svc;


-- =============================================================================
--  3. Schéma ORDERS (service Commandes)
-- =============================================================================
SET ROLE orders_svc;            -- [+] on "devient" orders_svc : les tables créées lui appartiennent
SET search_path = orders;       --     et on peut écrire "customers" au lieu de "orders.customers"

CREATE TABLE IF NOT EXISTS customers (
    id     SERIAL PRIMARY KEY,                -- SERIAL = entier qui s'incrémente tout seul
    name   TEXT NOT NULL,                     -- NOT NULL = valeur obligatoire
    email  TEXT UNIQUE NOT NULL               -- UNIQUE = pas deux clients avec le même email
);

CREATE TABLE IF NOT EXISTS orders (
    id           SERIAL PRIMARY KEY,
    -- REFERENCES = clé étrangère : le client doit exister.
    -- [+] ON DELETE RESTRICT (au lieu de CASCADE) : supprimer un client n'efface pas
    --     ses commandes, donc pas l'historique des ventes. La suppression est refusée.
    customer_id  INTEGER NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    -- CHECK = règle vérifiée à chaque écriture.
    -- [+] 'DELIVERED' ajouté : l'onglet Commandes affiche le statut "livrée".
    status       TEXT NOT NULL CHECK (status IN ('PENDING', 'PAID', 'PREPARING', 'SHIPPED',
                                                 'DELIVERED', 'CANCELLED', 'PAYMENT_FAILED')),
    total_cents  INTEGER NOT NULL CHECK (total_cents >= 0),     -- montant en centimes, jamais négatif
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()             -- [+] NOT NULL : une commande a toujours une date
);

CREATE TABLE IF NOT EXISTS order_items (
    id                SERIAL PRIMARY KEY,
    order_id          INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,  -- lignes supprimées avec la commande
    product_id        INTEGER NOT NULL,       -- clé applicative vers MongoDB / Inventory (aucune base ne la vérifie)
    quantity          INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents  INTEGER NOT NULL CHECK (unit_price_cents >= 0),            -- prix copié au moment de l'achat
    -- [+] Un produit n'apparaît qu'une fois par commande (on augmente la quantité).
    CONSTRAINT order_items_order_product_key UNIQUE (order_id, product_id)
);

-- [+] Idempotence de POST /orders : si le client renvoie la même commande
--     (double-clic, réseau coupé), la clé déjà connue renvoie la commande existante.
CREATE TABLE IF NOT EXISTS idempotency_keys (
    key         UUID PRIMARY KEY,             -- identifiant aléatoire envoyé par le client
    order_id    INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Un index est comme l'index d'un livre : il évite de lire toute la table.
CREATE INDEX IF NOT EXISTS idx_orders_customer       ON orders (customer_id);
CREATE INDEX IF NOT EXISTS idx_order_items_order     ON order_items (order_id);
CREATE INDEX IF NOT EXISTS idx_orders_status_created ON orders (status, created_at DESC);  -- [+] onglet Commandes
CREATE INDEX IF NOT EXISTS idx_order_items_product   ON order_items (product_id);          -- [+] meilleures ventes

RESET ROLE;                    
-- =============================================================================
--  4. Schéma INVENTORY (service Stock & Logistique)
-- =============================================================================
SET ROLE inventory_svc;
SET search_path = inventory;

CREATE TABLE IF NOT EXISTS warehouses (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,     -- [+] UNIQUE : pas deux entrepôts du même nom
    city            TEXT,                     -- [+] utile pour l'onglet Logistique
    -- [+] > 0 (au lieu de >= 0) : une capacité nulle ferait une division par zéro
    --     dans le calcul du taux de remplissage.
    capacity_units  INTEGER NOT NULL CHECK (capacity_units > 0)
);

CREATE TABLE IF NOT EXISTS stock (
    product_id           INTEGER NOT NULL,    -- clé applicative vers MongoDB
    -- [+] ON DELETE RESTRICT (au lieu de CASCADE) : supprimer un entrepôt n'efface
    --     pas son stock en silence.
    warehouse_id         INTEGER NOT NULL REFERENCES warehouses(id) ON DELETE RESTRICT,
    quantity             INTEGER NOT NULL CHECK (quantity >= 0),       -- stock physique
    -- [+] Réservation (Saga) : une partie du stock est mise de côté pour des
    --     commandes en cours. Stock disponible à la vente = quantity - reserved.
    reserved             INTEGER NOT NULL DEFAULT 0,
    low_stock_threshold  INTEGER NOT NULL DEFAULT 5 CHECK (low_stock_threshold >= 0),  -- [+] seuil d'alerte
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),                           -- [+]
    -- Clé composite : un produit peut être dans plusieurs entrepôts.
    PRIMARY KEY (product_id, warehouse_id),
    -- [+] On ne réserve jamais plus que le stock physique : la base l'interdit.
    CONSTRAINT stock_reserved_check CHECK (reserved >= 0 AND reserved <= quantity)
);

-- [+] Les réservations (Saga) : l'id est choisi par l'appelant, donc réserver deux
--     fois avec le même id ne réserve qu'une fois (idempotence). Si le paiement
--     échoue, la réservation passe à 'RELEASED' et le stock est rendu.
CREATE TABLE IF NOT EXISTS reservations (
    id            UUID PRIMARY KEY,
    order_id      INTEGER NOT NULL,           
    product_id    INTEGER NOT NULL,
    warehouse_id  INTEGER NOT NULL,
    quantity      INTEGER NOT NULL CHECK (quantity > 0),
    status        TEXT NOT NULL DEFAULT 'RESERVED'
                  CHECK (status IN ('RESERVED', 'RELEASED', 'COMMITTED')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (product_id, warehouse_id) REFERENCES stock (product_id, warehouse_id)
);

CREATE INDEX IF NOT EXISTS idx_stock_product      ON stock (product_id);
CREATE INDEX IF NOT EXISTS idx_stock_warehouse    ON stock (warehouse_id);       -- [+] "le stock de l'entrepôt X"
CREATE INDEX IF NOT EXISTS idx_reservations_order ON reservations (order_id);    -- [+]

-- [+] Onglet Logistique : taux de remplissage par entrepôt, alerte à 90 %.
--     Une VUE est une requête enregistrée qu'on interroge comme une table.
CREATE OR REPLACE VIEW warehouse_fill_rate AS
SELECT w.id, w.name, w.city, w.capacity_units,
       COALESCE(SUM(s.quantity), 0)                                       AS units_stored,
       ROUND(100.0 * COALESCE(SUM(s.quantity), 0) / w.capacity_units, 1)  AS fill_pct,
       CASE WHEN 100.0 * COALESCE(SUM(s.quantity), 0) / w.capacity_units >= 90
            THEN 'SATURATION_PROCHE' ELSE 'NORMAL' END                    AS status
FROM warehouses w
LEFT JOIN stock s ON s.warehouse_id = w.id     
GROUP BY w.id;

-- [+] Onglet Vue d'ensemble : produits bientôt en rupture, tous entrepôts confondus.
CREATE OR REPLACE VIEW low_stock AS
SELECT product_id,
       SUM(quantity - reserved) AS available,
       MIN(low_stock_threshold) AS threshold
FROM stock
GROUP BY product_id
HAVING SUM(quantity - reserved) <= MIN(low_stock_threshold);  

RESET ROLE;


-- =============================================================================
--  5. Schéma PAYMENTS (service Paiement)
-- =============================================================================
SET ROLE payments_svc;
SET search_path = payments;

CREATE TABLE IF NOT EXISTS payments (
    id               SERIAL PRIMARY KEY,
    order_id         INTEGER NOT NULL,        
    amount_cents     INTEGER NOT NULL CHECK (amount_cents >= 0),
    status           TEXT NOT NULL CHECK (status IN ('SUCCESS', 'FAILED', 'PENDING')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),          -- [+] NOT NULL
    -- [+] Idempotence de POST /payments : rejouer le même paiement (même clé) ne
    --     débite qu'une fois. UNIQUE fait échouer la seconde insertion.
    idempotency_key  UUID NOT NULL UNIQUE,
    -- [+] Savoir POURQUOI un paiement a échoué (montant trop élevé, carte refusée…).
    failure_reason   TEXT,
    CONSTRAINT payments_failure_reason_check
        CHECK (status <> 'FAILED' OR failure_reason IS NOT NULL)   
);

CREATE INDEX IF NOT EXISTS idx_payments_order          ON payments (order_id);
CREATE INDEX IF NOT EXISTS idx_payments_status_created ON payments (status, created_at DESC);  -- [+] onglet Paiements

-- La règle "refusé au-dessus de 3 000 €" n'est pas ici : c'est une règle métier
-- qui peut changer, elle vivra dans le code du service payments.

RESET ROLE;


-- =============================================================================
--  6. Schéma AUTH (service Auth - bonus)
-- =============================================================================

SET ROLE auth_svc;
SET search_path = auth;

CREATE TABLE IF NOT EXISTS users (
    id             SERIAL PRIMARY KEY,
    email          TEXT UNIQUE NOT NULL,
    password_hash  TEXT NOT NULL,             
    is_active      BOOLEAN DEFAULT TRUE,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS roles (
    id           SERIAL PRIMARY KEY,
    name         TEXT UNIQUE NOT NULL,
    description  TEXT
);

-- Table d'association "plusieurs à plusieurs" : un utilisateur peut avoir
-- plusieurs rôles, un rôle peut être donné à plusieurs utilisateurs.
CREATE TABLE IF NOT EXISTS user_roles (
    user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id  INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);

-- [+] Les rôles de l'équipe (RBAC).
INSERT INTO roles (name, description) VALUES
  ('admin',           'Gère la plateforme et les utilisateurs'),
  ('catalog_manager', 'Crée et modifie les produits et les prix'),
  ('logistics',       'Gère les stocks et les entrepôts, lit les commandes'),
  ('analyst',         'Lecture seule : tableaux de bord et rapports')
ON CONFLICT (name) DO NOTHING;      

RESET ROLE;
