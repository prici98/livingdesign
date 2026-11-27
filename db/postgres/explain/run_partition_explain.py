# =============================================================================
#  db/postgres/explain/run_partition_explain.py — prouver le "partition pruning"
# =============================================================================
#  Mesure une requête de l'onglet Vue d'ensemble : le nombre de commandes et le
#  chiffre d'affaires du mois en cours. On la lance deux fois :
#    • AVANT la migration 001 : orders est une table simple, tout est lu ;
#    • APRÈS la migration     : orders est partitionnée, seul le mois demandé est lu.
#
#  Le script détecte lui-même l'état de la table et remplit la section
#  correspondante de docs/partitions.md (l'autre section est conservée).
#
#  Lancer : uv run python db/postgres/explain/run_partition_explain.py
# =============================================================================

import re
import statistics
from datetime import date, datetime
from pathlib import Path

import psycopg

from livingdesign_commons import get_settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORT = PROJECT_ROOT / "docs" / "partitions.md"
RUNS = 5
settings = get_settings()


def month_bounds() -> tuple[date, date]:
    """Le 1er jour du mois courant et le 1er jour du mois suivant."""
    today = date.today()
    start = today.replace(day=1)
    end = date(start.year + (start.month == 12), start.month % 12 + 1, 1)   # gère le passage de décembre à janvier
    return start, end


def connect() -> psycopg.Connection:
    return psycopg.connect(
        host=settings.postgres_host, port=settings.postgres_port, dbname=settings.postgres_db,
        user="orders_svc", password=settings.orders_db_password.get_secret_value(),
    )


def scanned_tables(node: dict, found: list) -> list:
    """Parcourt tout l'arbre du plan et note chaque table réellement lue."""
    if "Relation Name" in node:                       # un nœud qui lit une table
        rows = node.get("Actual Rows", 0) + node.get("Rows Removed by Filter", 0)
        found.append((node["Relation Name"], node["Node Type"], int(rows)))
    for child in node.get("Plans", []):               # puis ses enfants, récursivement
        scanned_tables(child, found)
    return found


def measure(cur, sql: str) -> dict:
    times = []
    for _ in range(RUNS):
        cur.execute(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}")
        plan = cur.fetchone()[0][0]
        times.append(plan["Execution Time"])
    cur.execute(f"EXPLAIN (ANALYZE, BUFFERS) {sql}")
    text = "\n".join(row[0] for row in cur.fetchall())
    root = plan["Plan"]
    return {
        "time": statistics.median(times),
        "tables": scanned_tables(root, []),
        "buffers": root.get("Shared Hit Blocks", 0) + root.get("Shared Read Blocks", 0),
        "text": text,
    }


def section(label: str, sql: str, r: dict, counts: tuple) -> str:
    rows_read = sum(t[2] for t in r["tables"])
    names = ", ".join(f"`{t[0]}`" for t in r["tables"])
    lines = [
        f"<!-- {label} -->",
        f"## {'Après : table partitionnée par mois' if label == 'apres' else 'Avant : table simple'}",
        "",
        f"Mesuré le {datetime.now():%d/%m/%Y à %H:%M}, médiane de {RUNS} exécutions.",
        "",
        "| Mesure | Valeur |",
        "| --- | --- |",
        f"| Tables lues | {len(r['tables'])} : {names} |",
        f"| Lignes examinées | {rows_read:,} sur {counts[0]:,} commandes |".replace(",", " "),
        f"| Blocs lus (8 Ko) | {r['buffers']} |",
        f"| Temps d'exécution | {r['time']:.3f} ms |",
        "",
        "```", r["text"], "```",
        f"<!-- /{label} -->",
    ]
    return "\n".join(lines)


def write_report(label: str, new_section: str, sql: str) -> None:
    header = (
        "# Partitionnement des commandes — mesure EXPLAIN\n\n"
        "Généré par `db/postgres/explain/run_partition_explain.py`, lancé une fois avant et une fois après "
        "`services/orders/migrations/001_partition_orders_by_month.sql`.\n\n"
        "Requête mesurée (onglet Vue d'ensemble : commandes et chiffre d'affaires du mois en cours) :\n\n"
        f"```sql\n{sql}\n```\n"
    )
    old = REPORT.read_text(encoding="utf-8") if REPORT.exists() else ""
    # On récupère les deux sections déjà présentes, puis on remplace celle qu'on vient de mesurer.
    sections = {}
    for name in ("avant", "apres"):
        match = re.search(rf"<!-- {name} -->.*?<!-- /{name} -->", old, flags=re.S)   # re.S : "." traverse les lignes
        if match:
            sections[name] = match.group(0)
    sections[label] = new_section
    body = "\n\n".join(sections[n] for n in ("avant", "apres") if n in sections)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(header + "\n" + body + "\n", encoding="utf-8")


def main() -> None:
    start, end = month_bounds()
    # Dates écrites en toutes lettres dans la requête : PostgreSQL choisit les
    # partitions dès la préparation du plan, et le plan les affiche clairement.
    sql = (
        "SELECT count(*) AS commandes, sum(total_cents) AS ca_cents FROM orders.orders "
        f"WHERE created_at >= '{start}' AND created_at < '{end}'"
    )
    with connect() as conn, conn.cursor() as cur:
        # relkind 'p' = table partitionnée, 'r' = table simple.
        cur.execute("SELECT relkind FROM pg_class WHERE oid = 'orders.orders'::regclass")
        label = "apres" if cur.fetchone()[0] == "p" else "avant"
        cur.execute("SELECT count(*) FROM orders.orders")
        counts = cur.fetchone()
        result = measure(cur, sql)

    print(f"État de la table : {'partitionnée' if label == 'apres' else 'simple'}")
    for table, node, rows in result["tables"]:
        print(f"   lit {table:<22} ({node}, {rows} lignes examinées)")
    print(f"   blocs lus : {result['buffers']}   temps : {result['time']:.3f} ms")
    write_report(label, section(label, sql, result, counts), sql)
    print(f"✔ Section « {label} » écrite dans {REPORT.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
