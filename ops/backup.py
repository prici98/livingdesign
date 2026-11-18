# =============================================================================
#  ops/backup.py — sauvegarder PostgreSQL et MongoDB
# =============================================================================
#  Crée un dossier daté dans ops/backups/ avec :
#    postgres.dump        toute la base PostgreSQL (format "custom" de pg_dump)
#    mongo.archive.gz     toute la base MongoDB (archive compressée de mongodump)
#    manifest.json        la date et le nombre de lignes de chaque table
#
#  Le manifest sert de preuve : restore.py recompte les lignes après la
#  restauration et les compare à celles-ci.
#
#  Prérequis : les conteneurs tournent (docker compose -f infra/docker-compose.yml up -d)
#  Lancer    : uv run python ops/backup.py      (depuis la racine du projet)
# =============================================================================

import json
import shutil                                 # supprimer un dossier et son contenu
import subprocess
from datetime import datetime

from common import BACKUP_DIR, MONGO_AUTH, compose_exec, count_rows, print_counts

KEEP = 7        # politique de rétention : on garde les 7 sauvegardes les plus récentes


def dump_to_file(service: str, shell_command: str, target) -> None:
    """Lance une commande de sauvegarde dans un conteneur et écrit sa sortie dans un fichier."""
    # "wb" = écriture en binaire : une sauvegarde n'est pas du texte.
    with open(target, "wb") as f:
        # stdout=f : tout ce que la commande affiche part directement dans le fichier.
        subprocess.run(compose_exec(service, shell_command), stdout=f, check=True)


def remove_old_backups() -> None:
    # Les noms de dossiers sont des dates (2026-11-15_1530) : l'ordre alphabétique
    # est donc aussi l'ordre chronologique.
    backups = sorted(p for p in BACKUP_DIR.iterdir() if p.is_dir())
    for old in backups[:-KEEP]:                # [:-KEEP] = tous sauf les KEEP derniers
        shutil.rmtree(old)
        print(f"   (ancienne sauvegarde supprimée : {old.name})")


def main() -> None:
    target = BACKUP_DIR / datetime.now().strftime("%Y-%m-%d_%H%M%S")   # ex. 2026-11-15_153012
    target.mkdir(parents=True)

    print("1. Comptage des lignes avant sauvegarde…")
    counts = count_rows()
    print_counts(counts)

    print("2. Sauvegarde PostgreSQL (pg_dump)…")
    # -Fc = format "custom" : compressé, et pg_restore peut le relire table par table.
    dump_to_file("postgres", 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc', target / "postgres.dump")

    print("3. Sauvegarde MongoDB (mongodump)…")
    # --archive sans nom de fichier = écrire sur la sortie, --gzip = compresser.
    # --dumpDbUsersAndRoles : inclut l'utilisateur catalog_svc, sinon il serait perdu.
    dump_to_file(
        "mongo",
        f'mongodump --quiet --archive --gzip {MONGO_AUTH} --db "$MONGO_INITDB_DATABASE" --dumpDbUsersAndRoles',
        target / "mongo.archive.gz",
    )

    manifest = {"created_at": datetime.now().isoformat(timespec="seconds"), "counts": counts}
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    remove_old_backups()

    # stat().st_size = taille du fichier en octets ; // 1024 = en kilo-octets (division entière)
    sizes = ", ".join(f"{f.name} {f.stat().st_size // 1024} Ko" for f in sorted(target.iterdir()))
    print(f"✔ Sauvegarde terminée : {target}")
    print(f"   {sizes}")


if __name__ == "__main__":
    main()
