# =============================================================================
#  db/postgres/explain/run_explain.py — mesurer l'effet des index avec EXPLAIN
# =============================================================================
#  Le cahier des charges demande : « Ajoutez des index. Montrez une requête avant
#  et après avec la commande EXPLAIN. »
#
#  Pour chaque requête des onglets, le script :
#    1. la mesure SANS son index : il supprime l'index DANS une transaction,
#       lance EXPLAIN ANALYZE, puis annule la transaction (ROLLBACK). L'index
#       revient aussitôt : la base n'est jamais modifiée durablement ;
#    2. la mesure AVEC son index ;
#    3. écrit le résultat dans docs/explain.md (tableau + plans complets).
#
#  Chaque mesure est répétée 5 fois et on garde la médiane : la première
#  exécution est souvent plus lente (données pas encore en mémoire).
#
#  Prérequis : base remplie (db/postgres/seed/generate_fake_data.py)
#  Lancer    : uv run python db/postgres/explain/run_explain.py
# =============================================================================

import statistics                             # statistics.median : la valeur du milieu
from dataclasses import dataclass             # une petite classe qui ne stocke que des données
from datetime import datetime
from pathlib import Path

import psycopg

from livingdesign_commons import get_settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORT = PROJECT_ROOT / "docs" / "explain.md"
RUNS = 5                                      # nombre de mesures par cas
settings = get_settings()


@dataclass
class Case:
    """Une requête à mesurer, l'index qu'elle utilise et le rôle qui en est propriétaire."""

    title: str           # ce que la requête sert à afficher
    tab: str             # l'onglet de l'écran concerné
    role: str            # le rôle PostgreSQL propriétaire de la table (lui seul peut supprimer l'index)
    index: str           # l'index qu'on retire pour la mesure "avant"
    sql: str


# Les valeurs (client 42, produit 123…) sont fixes : relancer le script mesure
# exactement les mêmes requêtes.
CASES = [
    Case(
        title="Les 20 dernières commandes d'un client",
        tab="Commandes",
        role="orders_svc",
        index="orders.idx_orders_customer",
        sql="SELECT id, status, total_cents, created_at FROM orders.orders "
            "WHERE customer_id = 42 ORDER BY created_at DESC LIMIT 20",
    ),
    Case(
        title="Les 50 derniers paiements en échec",
        tab="Commandes",
        role="orders_svc",
        index="orders.idx_orders_status_created",
        sql="SELECT id, customer_id, total_cents, created_at FROM orders.orders "
            "WHERE status = 'PAYMENT_FAILED' ORDER BY created_at DESC LIMIT 50",
    ),
    Case(
        title="Quantité vendue d'un produit",
        tab="Vue d'ensemble (meilleures ventes)",
        role="orders_svc",
        index="orders.idx_order_items_product",
        sql="SELECT sum(quantity) AS sold FROM orders.order_items WHERE product_id = 123",
    ),
    Case(
        # Ce cas sert à vérifier un index du script fourni : la clé primaire de
        # stock est (product_id, warehouse_id), elle commence donc déjà par
        # product_id. Si le plan "avant" utilise la clé primaire, idx_stock_product
        # est inutile.
        title="Stock d'un produit dans tous les entrepôts",
        tab="Catalogue / Logistique",
        role="inventory_svc",
        index="inventory.idx_stock_product",
        sql="SELECT warehouse_id, quantity, reserved FROM inventory.stock WHERE product_id = 123",
    ),
]

PASSWORDS = {
    "orders_svc": settings.orders_db_password,
    "inventory_svc": settings.inventory_db_password,
}


def connect(role: str) -> psycopg.Connection:
    return psycopg.connect(
        host=settings.postgres_host, port=settings.postgres_port, dbname=settings.postgres_db,
        user=role, password=PASSWORDS[role].get_secret_value(),
    )


def measure(cur, sql: str) -> tuple[float, str, str]:
    """Renvoie (temps médian en ms, type d'accès principal, plan lisible)."""
    times = []
    for _ in range(RUNS):
        # FORMAT JSON : un plan facile à lire pour un programme.
        cur.execute(f"EXPLAIN (ANALYZE, FORMAT JSON) {sql}")
        plan = cur.fetchone()[0][0]                  # psycopg convertit déjà le JSON en dict
        times.append(plan["Execution Time"])         # temps réel d'exécution, en millisecondes

    # Le plan texte (ce qu'on montre au jury), mesuré une dernière fois.
    # BUFFERS : combien de blocs de 8 Ko PostgreSQL a dû lire.
    cur.execute(f"EXPLAIN (ANALYZE, BUFFERS) {sql}")
    text_plan = "\n".join(row[0] for row in cur.fetchall())
    return statistics.median(times), scan_type(plan["Plan"]), text_plan


def scan_type(node: dict) -> str:
    """Descend dans le plan jusqu'à la lecture de la table : Seq Scan, Index Scan…"""
    # Un plan est un arbre : chaque nœud peut avoir des enfants ("Plans").
    # On suit le premier enfant jusqu'à la feuille, qui est la lecture des données.
    while node.get("Plans"):
        node = node["Plans"][0]
    name = node["Node Type"]
    if "Index Name" in node:                         # quel index a été utilisé ?
        name += f" ({node['Index Name']})"
    return name


def run_case(case: Case) -> dict:
    with connect(case.role) as conn, conn.cursor() as cur:
        # --- AVANT : sans l'index, dans une transaction annulée ensuite ---
        cur.execute(f"DROP INDEX {case.index}")
        before = measure(cur, case.sql)
        conn.rollback()                              # annule le DROP : l'index revient

        # --- APRÈS : avec l'index ---
        after = measure(cur, case.sql)
        conn.rollback()                              # rien à garder (EXPLAIN ANALYZE d'un SELECT ne modifie rien)
    return {"case": case, "before": before, "after": after}


def table_sizes() -> dict[str, int]:
    with connect("orders_svc") as conn, conn.cursor() as cur:
        cur.execute("SELECT (SELECT count(*) FROM orders.orders), (SELECT count(*) FROM orders.order_items)")
        orders, items = cur.fetchone()
    with connect("inventory_svc") as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM inventory.stock")
        stock = cur.fetchone()[0]
    return {"orders.orders": orders, "orders.order_items": items, "inventory.stock": stock}


def gain_label(t_before: float, scan_before: str, t_after: float) -> str:
    # Si, même sans l'index testé, PostgreSQL utilisait déjà un AUTRE index
    # (la clé primaire par exemple), l'index testé n'apporte rien : il est redondant.
    if not scan_before.startswith(("Seq Scan", "Parallel Seq Scan")):
        return "aucun : un autre index suffit déjà"
    return f"× {t_before / t_after:.0f}" if t_after > 0 else "—"


def write_report(results: list[dict], sizes: dict[str, int]) -> None:
    lines = [
        "# Effet des index — mesures EXPLAIN ANALYZE",
        "",
        f"Généré le {datetime.now():%d/%m/%Y à %H:%M} par `db/postgres/explain/run_explain.py`. "
        f"Temps = médiane de {RUNS} exécutions.",
        "",
        "Volume mesuré : " + ", ".join(f"`{t}` {n:,} lignes".replace(",", " ") for t, n in sizes.items()) + ".",
        "",
        "| Requête | Onglet | Sans index | Avec index | Gain |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in results:
        (t_before, scan_before, _), (t_after, scan_after, _) = r["before"], r["after"]
        lines.append(
            f"| {r['case'].title} | {r['case'].tab} | {t_before:.3f} ms — {scan_before} "
            f"| {t_after:.3f} ms — {scan_after} | {gain_label(t_before, scan_before, t_after)} |"
        )
    lines += ["", "## Plans complets", ""]
    for r in results:
        c = r["case"]
        lines += [
            f"### {c.title}", "",
            f"Index testé : `{c.index}`", "",
            "```sql", c.sql, "```", "",
            "**Sans index**", "", "```", r["before"][2], "```", "",
            "**Avec index**", "", "```", r["after"][2], "```", "",
        ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    sizes = table_sizes()
    print(f"Volume : {sizes}")
    results = []
    for case in CASES:
        print(f"→ {case.title}…")
        result = run_case(case)
        (tb, sb, _), (ta, sa, _) = result["before"], result["after"]
        print(f"   sans index : {tb:8.3f} ms  {sb}")
        print(f"   avec index : {ta:8.3f} ms  {sa}   gain : {gain_label(tb, sb, ta)}")
        results.append(result)
    write_report(results, sizes)
    print(f"✔ Rapport écrit : {REPORT.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
