# =============================================================================
#  LivingDesign — Étape 2b : générer les données transactionnelles fictives
# =============================================================================
#  Le dataset IKEA ne contient que des produits. Pour faire vivre la plateforme,
#  on fabrique des données FICTIVES mais COHÉRENTES avec le catalogue :
#    • inventory : 4 entrepôts + le stock de chaque produit
#    • orders    : des clients, des commandes, des lignes de commande
#    • payments  : un paiement par commande (refusé au-dessus de 3 000 €)
#
#  Cohérence : les product_id et les prix viennent de products.jsonl, comme le
#  catalogue MongoDB. Une ligne de commande pointe donc toujours vers un vrai produit.
#
#  Chaque schéma est rempli avec le rôle de SON service (orders_svc, etc.).
#  À la fin, le script vérifie qu'un service ne peut PAS lire les tables d'un autre.
#
#  Prérequis : docker compose -f infra/docker-compose.yml up -d
#              et python data-platform/jobs-spark/ingest_dataset.py
#  Lancer    : python db/postgres/seed/generate_fake_data.py   (depuis la racine ;
#              relançable : vide puis recharge)
# =============================================================================

import math                                   
import random                                
import uuid                                 
from datetime import UTC, datetime, timedelta    
from pathlib import Path

import psycopg                               
from faker import Faker                      

from livingdesign_commons import Category, Product, get_settings   


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PRODUCTS_FILE = PROJECT_ROOT / "data-platform" / "data" / "clean" / "products.jsonl"
settings = get_settings()          

# --- Reproductibilité --------------------------------------------------------
# "seed" = la graine du hasard. Avec la même graine, random tire TOUJOURS la même
# suite de nombres : relancer le script redonne exactement les mêmes données.
random.seed(42)
fake = Faker("fr_FR")                       
Faker.seed(42)

# --- Paramètres (lus dans infra/.env par Pydantic, déjà convertis en int) ------
N_CUSTOMERS = settings.seed_customers
N_ORDERS = settings.seed_orders
N_MONTHS = settings.seed_months
PAYMENT_LIMIT_CENTS = 300_000                
NOW = datetime.now(UTC)             

# Catégories encombrantes : moins d'unités en stock, seuil d'alerte plus bas.
BULKY = {Category.CANAPES, Category.LITS, Category.TABLES, Category.RANGEMENT}


# Le mot de passe de chaque rôle, lu dans la configuration Pydantic.
PASSWORDS = {
    "orders_svc": settings.orders_db_password,
    "inventory_svc": settings.inventory_db_password,
    "payments_svc": settings.payments_db_password,
}


def connect(role: str) -> psycopg.Connection:
    """Ouvre une connexion PostgreSQL avec le rôle d'un service."""
    return psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=role,
        password=PASSWORDS[role].get_secret_value(),  
    )


def read_products() -> list[Product]:
    if not PRODUCTS_FILE.exists():
        raise SystemExit("products.jsonl introuvable : lance d'abord "
                         "python data-platform/jobs-spark/ingest_dataset.py")
    with open(PRODUCTS_FILE, encoding="utf-8") as f:
        return [Product.model_validate_json(line) for line in f]


# =============================================================================
#  1. Inventory : entrepôts et stock
# =============================================================================
WAREHOUSES = [  # (nom, ville, taux de remplissage visé)
    ("LD-PARIS",    "Paris",    0.93), 
    ("LD-LYON",     "Lyon",     0.71),
    ("LD-LILLE",    "Lille",    0.58),
    ("LD-BORDEAUX", "Bordeaux", 0.80),
]


def seed_inventory(products: list[Product]) -> None:
    rows = []                                          
    for p in products:
        # p est un objet Product : on lit ses champs avec un point (p.category),
        # et l'éditeur peut vérifier le nom du champ, contrairement à p["category"].
        bulky = p.category in BULKY
        # Chaque produit est stocké dans 1 à 3 entrepôts tirés au hasard.
        # random.sample(liste, k) tire k éléments DIFFÉRENTS.
        warehouses = random.sample(range(1, len(WAREHOUSES) + 1), k=random.randint(1, 3))
        for warehouse_id in warehouses:
            if random.random() < 0.06:              
                quantity = random.randint(0, 3)        
            elif bulky:
                quantity = random.randint(5, 60)     
            else:
                quantity = random.randint(30, 400)    
            threshold = 3 if bulky else 10
            rows.append((p.product_id, warehouse_id, quantity, threshold))

    # La capacité de chaque entrepôt est calculée pour atteindre le taux visé.
    total_by_warehouse = {i: 0 for i in range(1, len(WAREHOUSES) + 1)}  
    for _, warehouse_id, quantity, _ in rows:          
        total_by_warehouse[warehouse_id] += quantity

    # "with" ouvre la connexion et la ferme à la fin. Si tout s'est bien passé,
    # psycopg valide la transaction (COMMIT) ; en cas d'erreur, il annule tout (ROLLBACK).
    with connect("inventory_svc") as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE reservations, stock, warehouses RESTART IDENTITY")

        for warehouse_id, (name, city, target) in enumerate(WAREHOUSES, start=1):
            capacity = math.ceil(total_by_warehouse[warehouse_id] / target)
        
            cur.execute(
                "INSERT INTO warehouses (id, name, city, capacity_units) VALUES (%s, %s, %s, %s)",
                (warehouse_id, name, city, capacity),
            )
       
        cur.execute("SELECT setval('warehouses_id_seq', (SELECT max(id) FROM warehouses))")

        # COPY : la méthode la plus rapide pour charger beaucoup de lignes d'un coup.
        with cur.copy("COPY stock (product_id, warehouse_id, quantity, low_stock_threshold) FROM STDIN") as copy:
            for row in rows:
                copy.write_row(row)

        cur.execute("SELECT count(*) FROM low_stock") 
        low = cur.fetchone()[0]                       

    print(f"✔ inventory : {len(WAREHOUSES)} entrepôts, {len(rows)} lignes de stock, "
          f"{low} produits bientôt en rupture")


# =============================================================================
#  2. Orders + payments : clients, commandes, lignes, paiements
# =============================================================================
def random_order_time() -> datetime:
    """Une date de commande réaliste : plus récente, plutôt le soir."""
    
    days_ago = random.random() ** 1.3 * N_MONTHS * 30
    day = NOW - timedelta(days=days_ago)
    # random.choices avec des poids : les heures du soir sont plus probables.
    hour = random.choices(range(24), weights=[1, 1, 1, 1, 1, 1, 2, 3, 4, 5, 6, 7,
                                              8, 7, 6, 6, 7, 8, 10, 12, 13, 11, 7, 3])[0]
    moment = day.replace(hour=hour, minute=random.randint(0, 59), second=random.randint(0, 59),
                         microsecond=0)
    return min(moment, NOW - timedelta(minutes=1))    


def status_for(created: datetime, paid: bool) -> str:
    """Le statut dépend du paiement et de l'âge de la commande."""
    if not paid:
        return "PAYMENT_FAILED"
    age = NOW - created                              
    if age > timedelta(days=10):
        return "CANCELLED" if random.random() < 0.02 else "DELIVERED"
    if age > timedelta(days=3):
        return "SHIPPED"
    if age > timedelta(hours=6):
        return "PREPARING"
    return "PAID"


def seed_orders_and_payments(products: list[Product]) -> None:
    # --- Les produits qu'on peut commander, et leur "popularité" ---
    sellable = [p for p in products if p.status == "active"]
    # Les petits prix se vendent plus souvent : poids inversement proportionnel au prix.
    weights = [(5_000 / p.price_cents) ** 0.45 for p in sellable]

    # --- Clients ---
    customers = []
    for customer_id in range(1, N_CUSTOMERS + 1):
        first, last = fake.first_name(), fake.last_name()
        slug = f"{first}.{last}".lower().replace(" ", "").replace("'", "")
        email = f"{slug}.{customer_id}@example.com"
        customers.append((customer_id, f"{first} {last}", email))

    # --- Commandes, lignes et paiements ---
    orders, items, payments = [], [], []
    for order_id in range(1, N_ORDERS + 1):
        created = random_order_time()
        n_lines = random.choices([1, 2, 3, 4], weights=[50, 30, 14, 6])[0]
        chosen = random.choices(sellable, weights=weights, k=n_lines)

        seen, total = set(), 0
        for p in chosen:
            if p.product_id in seen:               
                continue
            seen.add(p.product_id)
            quantity = random.choices([1, 2, 4], weights=[85, 12, 3])[0]
            total += quantity * p.price_cents
        
            items.append((order_id, p.product_id, quantity, p.price_cents))

        # Règle métier de LivingDesign : paiement refusé au-dessus de 3 000 €,
        # et 2 % de cartes refusées au hasard.
        if total > PAYMENT_LIMIT_CENTS:
            paid, reason = False, "amount_above_limit"
        elif random.random() < 0.02:
            paid, reason = False, "card_declined"
        else:
            paid, reason = True, None

        customer_id = random.randint(1, N_CUSTOMERS)
        orders.append((order_id, customer_id, status_for(created, paid), total, created))
        payments.append((
            order_id, total,
            "SUCCESS" if paid else "FAILED",         
            reason,
            str(uuid.uuid4()),                        
            created + timedelta(seconds=random.randint(2, 40)),  
        ))

    # --- Écriture dans le schéma orders, avec le rôle orders_svc ---
    with connect("orders_svc") as conn, conn.cursor() as cur:
        # CASCADE : vide aussi les tables qui dépendent de celles-ci.
        cur.execute("TRUNCATE idempotency_keys, order_items, orders, customers RESTART IDENTITY CASCADE")
        with cur.copy("COPY customers (id, name, email) FROM STDIN") as copy:
            for row in customers:
                copy.write_row(row)
        with cur.copy("COPY orders (id, customer_id, status, total_cents, created_at) FROM STDIN") as copy:
            for row in orders:
                copy.write_row(row)
        with cur.copy("COPY order_items (order_id, product_id, quantity, unit_price_cents) FROM STDIN") as copy:
            for row in items:
                copy.write_row(row)
        cur.execute("SELECT setval('customers_id_seq', (SELECT max(id) FROM customers))")
        cur.execute("SELECT setval('orders_id_seq', (SELECT max(id) FROM orders))")
      
        cur.execute("ANALYZE customers")
        cur.execute("ANALYZE orders")
        cur.execute("ANALYZE order_items")
    print(f"✔ orders    : {len(customers)} clients, {len(orders)} commandes, {len(items)} lignes")

    # --- Écriture dans le schéma payments, avec le rôle payments_svc ---
    with connect("payments_svc") as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE payments RESTART IDENTITY")
        columns = "order_id, amount_cents, status, failure_reason, idempotency_key, created_at"
        with cur.copy(f"COPY payments ({columns}) FROM STDIN") as copy:
            for row in payments:
                copy.write_row(row)
        cur.execute("SELECT status, count(*) FROM payments GROUP BY status ORDER BY status")
        summary = ", ".join(f"{status} = {count}" for status, count in cur.fetchall())
    print(f"✔ payments  : {summary}")


# =============================================================================
#  3. Vérifier l'isolation entre services
# =============================================================================
def check_isolation() -> None:
    with connect("orders_svc") as conn, conn.cursor() as cur:
        try:
            cur.execute("SELECT 1 FROM inventory.stock LIMIT 1")  
        except psycopg.errors.InsufficientPrivilege:              
            print("✔ isolation : orders_svc ne peut pas lire inventory.stock (permission refusée)")
            return                                                 
    raise SystemExit("✘ isolation : orders_svc a pu lire inventory.stock !")


def main():
    products = read_products()
    print(f"{len(products)} produits lus dans {PRODUCTS_FILE.name}")
    seed_inventory(products)
    seed_orders_and_payments(products)
    check_isolation()
    print("Terminé.")


if __name__ == "__main__":
    main()
