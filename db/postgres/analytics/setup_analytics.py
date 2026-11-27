# =============================================================================
#  db/postgres/analytics/setup_analytics.py — créer le schéma analytics
#  sur une base qui existe déjà
# =============================================================================
#  Les scripts de db/postgres/init/ ne tournent que sur une base neuve. Pour ne
#  pas tout effacer, ce script exécute livingdesign_analytics.sql dans le conteneur
#  PostgreSQL, en administrateur. Il peut être relancé sans risque.
#
#  Prérequis : ANALYTICS_DB_PASSWORD dans infra/.env, puis
#              docker compose -f infra/docker-compose.yml up -d
#              (le conteneur doit connaître la nouvelle variable)
#  Lancer    : uv run python db/postgres/analytics/setup_analytics.py
# =============================================================================

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SQL_FILE = PROJECT_ROOT / "db" / "postgres" / "init" / "livingdesign_analytics.sql"
COMPOSE_FILE = PROJECT_ROOT / "infra" / "docker-compose.yml"


def main() -> None:
    command = [
        "docker", "compose", "-f", str(COMPOSE_FILE), "exec", "-T", "postgres",
        "sh", "-c", 'psql -v ON_ERROR_STOP=1 -q -U "$POSTGRES_USER" -d "$POSTGRES_DB"',
    ]
    with open(SQL_FILE, "rb") as f:                      # le fichier SQL est envoyé à psql par stdin
        result = subprocess.run(command, stdin=f)
    if result.returncode != 0:
        sys.exit("✘ Échec. ANALYTICS_DB_PASSWORD est-il dans infra/.env, et le conteneur a-t-il été relancé (up -d) ?")
    print("✔ Schéma analytics prêt (rôle analytics_svc, tables orders_per_minute, category_views_per_minute, alerts)")


if __name__ == "__main__":
    main()
