# =============================================================================
#  services/orders/migrations/migrate.py — appliquer les migrations du schéma orders
# =============================================================================
#  Une migration est un fichier SQL numéroté (001_…, 002_…) qui fait évoluer le
#  schéma APRÈS sa création initiale (db/postgres/init). On ne modifie jamais une
#  base à la main : on écrit une migration, versionnée avec le code.
#
#  Ce script :
#    1. crée la table orders.schema_migrations, qui note les migrations déjà faites ;
#    2. applique, dans l'ordre, chaque fichier NNN_*.sql pas encore appliqué ;
#    3. exécute chaque migration dans UNE transaction : si elle échoue, rien
#       n'est modifié et le script s'arrête.
#
#  Relancer le script ne refait jamais une migration déjà appliquée.
#
#  Il se connecte avec orders_svc, le rôle propriétaire du schéma orders.
#
#  Lancer : uv run python services/orders/migrations/migrate.py
# =============================================================================

import sys
from pathlib import Path

import psycopg

from livingdesign_commons import get_settings

MIGRATIONS_DIR = Path(__file__).resolve().parent
settings = get_settings()


def connect() -> psycopg.Connection:
    return psycopg.connect(
        host=settings.postgres_host, port=settings.postgres_port, dbname=settings.postgres_db,
        user="orders_svc", password=settings.orders_db_password.get_secret_value(),
    )


def main() -> None:
    # sorted : 001 avant 002. glob("[0-9][0-9][0-9]_*.sql") = les fichiers qui
    # commencent par trois chiffres puis un "_".
    files = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"))

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS orders.schema_migrations (
                    version     text PRIMARY KEY,                  -- ex. "001"
                    name        text NOT NULL,                     -- le nom du fichier
                    applied_at  timestamptz NOT NULL DEFAULT now()
                )""")
            cur.execute("SELECT version FROM orders.schema_migrations")
            done = {row[0] for row in cur.fetchall()}          # ensemble des versions déjà appliquées
        conn.commit()

        pending = [f for f in files if f.name[:3] not in done]
        if not pending:
            print("✔ Aucune migration à appliquer : le schéma orders est à jour.")
            return

        for path in pending:
            version = path.name[:3]
            print(f"→ {path.name}…")
            try:
                with conn.cursor() as cur:
                    # Le fichier entier est envoyé en une fois (plusieurs instructions SQL).
                    cur.execute(path.read_text(encoding="utf-8"))
                    cur.execute(
                        "INSERT INTO orders.schema_migrations (version, name) VALUES (%s, %s)",
                        (version, path.name),
                    )
                conn.commit()                                  # tout ou rien
            except psycopg.Error as error:
                conn.rollback()                                # annule toute la migration
                sys.exit(f"✘ {path.name} a échoué, rien n'a été modifié :\n{error}")
            print(f"✔ {path.name} appliquée")


if __name__ == "__main__":
    main()
