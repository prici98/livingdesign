# =============================================================================
#  data-platform/streaming/producer.py — simuler l'activité du site dans Kafka
# =============================================================================
#  Tant que les services orders et inventory ne publient pas encore leurs
#  événements, ce script joue leur rôle : il envoie dans Kafka des clics, des
#  commandes et des mises à jour de stock réalistes, au format des contrats de
#  contracts/events/.
#
#  Il part de VRAIES données :
#    • le catalogue nettoyé (products.jsonl) pour les produits, prix, catégories ;
#    • le stock actuel, lu dans PostgreSQL avec le rôle inventory_svc (il joue le
#      service inventory, il a donc le droit de lire SON schéma).
#  Il ne modifie pas la base : le stock baisse seulement dans sa simulation.
#
#  Lancer (Kafka doit tourner) :
#    uv run python data-platform/streaming/producer.py                    # 60 s, 20 événements/s
#    uv run python data-platform/streaming/producer.py --seconds 300 --rate 50
#    uv run python data-platform/streaming/producer.py --spike            # pic de commandes → alerte ORDER_SPIKE
#    uv run python data-platform/streaming/producer.py --late 0.05        # 5 % d'événements en retard (watermark)
# =============================================================================

import argparse
import json
import random
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRODUCTS_FILE = PROJECT_ROOT / "data-platform" / "data" / "clean" / "products.jsonl"

TOPICS = {
    "clickstream": "livingdesign.clickstream",
    "orders": "livingdesign.orders",
    "stock": "livingdesign.stock",
    "alerts": "livingdesign.alerts",
}
PAYMENT_LIMIT_CENTS = 300_000          # même règle que le service payments : refus au-dessus de 3 000 €
SEARCH_WORDS = ["canapé", "lampe", "table", "étagère", "tapis", "chaise", "lit", "miroir", "coussin", "vase"]


def now_iso(shift_seconds: float = 0) -> str:
    """L'heure actuelle en UTC au format ISO 8601, décalée si besoin (événements en retard)."""
    return (datetime.now(UTC) - timedelta(seconds=shift_seconds)).isoformat()


class Simulation:
    """Fabrique des événements cohérents entre eux (même catalogue, même stock)."""

    def __init__(self, products: list[dict], stock: dict[tuple[int, int], dict], late_ratio: float = 0.0):
        self.products = [p for p in products if p["status"] == "active"]
        self.by_id = {p["product_id"]: p for p in self.products}
        self.stock = stock                       # {(product_id, warehouse_id): {"quantity", "reserved", "threshold"}}
        self.late_ratio = late_ratio
        self.next_order_id = 10_000_000          # loin des commandes de la base : aucune confusion possible
        # Comme pour les vraies ventes : les petits prix se vendent plus souvent.
        self.weights = [(5_000 / p["price_cents"]) ** 0.45 for p in self.products]

    def _occurred_at(self) -> str:
        # Une petite part des événements "arrive en retard" de 1 à 4 minutes :
        # ceux de plus de 2 minutes seront ignorés par le watermark de Spark.
        if random.random() < self.late_ratio:
            return now_iso(shift_seconds=random.uniform(60, 240))
        return now_iso()

    def click(self) -> dict:
        product = random.choices(self.products, weights=self.weights)[0]
        action = random.choices(["page_view", "search", "add_to_cart"], weights=[75, 15, 10])[0]
        return {
            "event_id": str(uuid.uuid4()),
            "event_type": "clickstream",
            "occurred_at": self._occurred_at(),
            "session_id": f"s-{random.randint(1, 500)}",
            "customer_id": random.choice([None, random.randint(1, 3000)]),
            "action": action,
            "product_id": None if action == "search" else product["product_id"],
            "category": None if action == "search" else product["category"],
            "query": random.choice(SEARCH_WORDS) if action == "search" else None,
        }

    def order(self) -> tuple[dict, list[dict]]:
        """Une commande, et les mises à jour de stock qu'elle provoque."""
        chosen = random.choices(self.products, weights=self.weights, k=random.choices([1, 2, 3], [60, 30, 10])[0])
        items, stock_events = {}, []
        for p in chosen:
            items[p["product_id"]] = {"product_id": p["product_id"], "quantity": random.choices([1, 2], [85, 15])[0],
                                      "unit_price_cents": p["price_cents"]}
        total = sum(i["quantity"] * i["unit_price_cents"] for i in items.values())
        paid = total <= PAYMENT_LIMIT_CENTS and random.random() > 0.02
        self.next_order_id += 1
        occurred_at = self._occurred_at()
        if paid:                                 # une commande payée fait baisser le stock
            for item in items.values():
                event = self._take_stock(item["product_id"], item["quantity"])
                if event:
                    stock_events.append(event)
        order = {
            "event_id": str(uuid.uuid4()),
            "event_type": "order-created",
            "occurred_at": occurred_at,
            "order_id": self.next_order_id,
            "customer_id": random.randint(1, 3000),
            "status": "PAID" if paid else "PAYMENT_FAILED",
            "total_cents": total,
            "items": list(items.values()),
        }
        return order, stock_events

    def _take_stock(self, product_id: int, quantity: int) -> dict | None:
        # On prend dans l'entrepôt qui a le plus de stock disponible pour ce produit.
        places = [(k, v) for k, v in self.stock.items() if k[0] == product_id]
        if not places:
            return None
        (pid, warehouse_id), line = max(places, key=lambda kv: kv[1]["quantity"] - kv[1]["reserved"])
        line["quantity"] = max(0, line["quantity"] - quantity)
        return self.stock_event(pid, warehouse_id)

    def stock_event(self, product_id: int, warehouse_id: int) -> dict:
        line = self.stock[(product_id, warehouse_id)]
        return {
            "event_id": str(uuid.uuid4()),
            "event_type": "stock-updated",
            "occurred_at": now_iso(),
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "quantity": line["quantity"],
            "reserved": min(line["reserved"], line["quantity"]),
            "low_stock_threshold": line["threshold"],
        }


# =============================================================================
#  Données de départ
# =============================================================================
def load_products() -> list[dict]:
    if not PRODUCTS_FILE.exists():
        raise SystemExit("products.jsonl introuvable : lance d'abord data-platform/jobs-spark/ingest_dataset.py")
    with open(PRODUCTS_FILE, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def load_stock() -> dict[tuple[int, int], dict]:
    import psycopg                                   # importé ici : les tests n'en ont pas besoin

    from livingdesign_commons import get_settings

    s = get_settings()
    with psycopg.connect(host=s.postgres_host, port=s.postgres_port, dbname=s.postgres_db, user="inventory_svc",
                         password=s.inventory_db_password.get_secret_value()) as conn, conn.cursor() as cur:
        cur.execute("SELECT product_id, warehouse_id, quantity, reserved, low_stock_threshold FROM inventory.stock")
        return {(r[0], r[1]): {"quantity": r[2], "reserved": r[3], "threshold": r[4]} for r in cur.fetchall()}


# =============================================================================
#  Envoi dans Kafka
# =============================================================================
def create_topics(bootstrap: str) -> None:
    from confluent_kafka.admin import AdminClient, NewTopic

    admin = AdminClient({"bootstrap.servers": bootstrap})
    existing = set(admin.list_topics(timeout=10).topics)
    # 3 partitions par topic : Kafka peut répartir le travail entre 3 consommateurs.
    missing = [NewTopic(t, num_partitions=3, replication_factor=1) for t in TOPICS.values() if t not in existing]
    for topic, future in admin.create_topics(missing).items() if missing else []:
        future.result()                              # attend la création (ou lève une erreur)
        print(f"   topic créé : {topic}")


def main() -> None:
    from confluent_kafka import Producer

    parser = argparse.ArgumentParser(description="Simule l'activité de LivingDesign dans Kafka")
    parser.add_argument("--bootstrap", default="localhost:9094", help="adresse de Kafka vue depuis ton PC")
    parser.add_argument("--seconds", type=int, default=60, help="durée de la simulation")
    parser.add_argument("--rate", type=int, default=20, help="événements par seconde (clics + commandes)")
    parser.add_argument("--late", type=float, default=0.0, help="part d'événements en retard, ex. 0.05")
    parser.add_argument("--spike", action="store_true", help="envoie un pic de commandes (alerte ORDER_SPIKE)")
    args = parser.parse_args()

    random.seed()                                    # pas de graine fixe : chaque simulation est différente
    print("Chargement du catalogue et du stock…")
    sim = Simulation(load_products(), load_stock(), late_ratio=args.late)
    create_topics(args.bootstrap)

    # acks=all + idempotence : Kafka n'enregistre pas deux fois un message renvoyé
    # après une coupure réseau (côté producteur, chaque message est écrit une seule fois).
    producer = Producer({"bootstrap.servers": args.bootstrap, "acks": "all", "enable.idempotence": True})
    counts = {"clickstream": 0, "orders": 0, "stock": 0}

    def send(kind: str, key, event: dict) -> None:
        # La clé décide de la partition : tous les messages d'une même clé restent dans l'ordre.
        producer.produce(TOPICS[kind], key=str(key), value=json.dumps(event, ensure_ascii=False))
        counts[kind] += 1

    end = time.time() + args.seconds
    print(f"Envoi pendant {args.seconds} s, {args.rate} événements/s (Ctrl+C pour arrêter)…")
    try:
        while time.time() < end:
            started = time.time()
            for _ in range(args.rate):
                if random.random() < 0.9:            # 90 % de clics, 10 % de commandes
                    click = sim.click()
                    send("clickstream", click["session_id"], click)
                else:
                    order, stock_events = sim.order()
                    send("orders", order["order_id"], order)
                    for event in stock_events:
                        send("stock", event["warehouse_id"], event)
            if args.spike:                           # pic : 60 commandes d'un coup, puis rythme normal
                for _ in range(60):
                    order, stock_events = sim.order()
                    send("orders", order["order_id"], order)
                    for event in stock_events:
                        send("stock", event["warehouse_id"], event)
                args.spike = False
                print("   pic de 60 commandes envoyé")
            producer.poll(0)                         # traite les accusés de réception de Kafka
            time.sleep(max(0.0, 1 - (time.time() - started)))   # garde un rythme d'environ 1 seconde par tour
    except KeyboardInterrupt:
        print("\nArrêt demandé.")
    finally:
        producer.flush(10)                           # envoie ce qui reste en mémoire avant de quitter
    print(f"✔ Envoyés : {counts['clickstream']} clics, {counts['orders']} commandes, "
          f"{counts['stock']} mises à jour de stock")


if __name__ == "__main__":
    main()
