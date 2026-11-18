# =============================================================================
#  ops/common.py — ce que backup.py et restore.py ont en commun
# =============================================================================
#  Les outils de sauvegarde (pg_dump, mongodump…) sont DÉJÀ installés dans les
#  conteneurs Docker. Plutôt que de les installer sur ton PC, on les lance à
#  l'intérieur des conteneurs avec "docker compose exec".
#
#  Les mots de passe administrateur restent dans les conteneurs : on écrit
#  "$POSTGRES_USER" et c'est le shell DU CONTENEUR qui remplace la variable.
#  Rien de secret ne passe par ton terminal.
# =============================================================================

import json
import subprocess                            # lancer une autre commande depuis Python
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]   # ops/ -> la racine du projet
COMPOSE_FILE = PROJECT_ROOT / "infra" / "docker-compose.yml"
BACKUP_DIR = PROJECT_ROOT / "ops" / "backups"        # non versionné (.gitignore)

# Les tables comptées avant la sauvegarde et après la restauration.
# Si les nombres sont identiques, la restauration est prouvée.
TABLES = [
    "orders.customers",
    "orders.orders",
    "orders.order_items",
    "inventory.warehouses",
    "inventory.stock",
    "payments.payments",
    "auth.roles",
]

# Morceau de commande réutilisé pour se connecter à MongoDB en administrateur.
# Les $… sont remplacés DANS le conteneur, qui connaît ces variables.
MONGO_AUTH = (
    '-u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" '
    "--authenticationDatabase admin"
)


def compose_exec(service: str, shell_command: str) -> list[str]:
    """Construit la commande qui lance `shell_command` dans le conteneur `service`.

    -T désactive le "terminal interactif". Indispensable ici : avec un terminal,
    Docker modifierait les octets d'une sauvegarde binaire en les transmettant.
    """
    return ["docker", "compose", "-f", str(COMPOSE_FILE), "exec", "-T", service, "sh", "-c", shell_command]


def run_text(service: str, shell_command: str) -> str:
    """Lance une commande dans un conteneur et renvoie ce qu'elle affiche."""
    # check=True : si la commande échoue, Python lève une erreur au lieu de continuer.
    # capture_output=True + text=True : on récupère l'affichage sous forme de texte.
    result = subprocess.run(compose_exec(service, shell_command), check=True, capture_output=True, text=True)
    return result.stdout.strip()


def count_rows() -> dict[str, int]:
    """Compte les lignes de chaque table PostgreSQL et les documents du catalogue."""
    # Une seule requête qui renvoie un objet JSON : {"orders.orders": 20000, …}
    pairs = ", ".join(f"'{t}', (SELECT count(*) FROM {t})" for t in TABLES)
    sql = f"SELECT json_build_object({pairs})"
    # psql -A -t : affichage brut, sans titres ni bordures (juste le JSON).
    output = run_text("postgres", f'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "{sql}"')
    counts = json.loads(output)

    # mongosh --quiet --eval : exécute une ligne de JavaScript et affiche le résultat.
    catalog = run_text(
        "mongo",
        f'mongosh --quiet {MONGO_AUTH} "$MONGO_INITDB_DATABASE" --eval "db.catalog.countDocuments()"',
    )
    counts["mongo.catalog"] = int(catalog)
    return counts


def print_counts(counts: dict[str, int]) -> None:
    for name, value in counts.items():
        print(f"     {name:<22} {value:>7}")   # :<22 aligne à gauche, :>7 à droite
