# =============================================================================
#  ops/restore.py — restaurer une sauvegarde et PROUVER qu'elle est complète
# =============================================================================
#  ⚠ Remplace les données actuelles par celles de la sauvegarde.
#
#  Étapes :
#    1. choisir la sauvegarde (la plus récente, ou celle passée avec --from)
#    2. demander une confirmation (taper OUI)
#    3. PostgreSQL : supprimer la base, la recréer, la remplir (pg_restore)
#    4. MongoDB    : remplacer les collections et l'utilisateur (mongorestore)
#    5. recompter les lignes et les comparer au manifest de la sauvegarde
#
#  Lancer :
#    uv run python ops/restore.py                                   (la plus récente)
#    uv run python ops/restore.py --from ops/backups/2026-11-15_153012
# =============================================================================

import argparse                               # lire les options de la ligne de commande
import json
import subprocess
import sys
from pathlib import Path

from common import BACKUP_DIR, MONGO_AUTH, compose_exec, count_rows, print_counts, run_text


def choose_backup(path: str | None) -> Path:
    if path:                                   # l'utilisateur a précisé --from
        backup = Path(path).resolve()
    else:                                      # sinon : le dossier le plus récent
        backups = sorted(p for p in BACKUP_DIR.glob("*") if p.is_dir()) if BACKUP_DIR.exists() else []
        if not backups:
            sys.exit("Aucune sauvegarde dans ops/backups/ : lance d'abord ops/backup.py")
        backup = backups[-1]                   # [-1] = le dernier élément de la liste
    for name in ("postgres.dump", "mongo.archive.gz", "manifest.json"):
        if not (backup / name).is_file():
            sys.exit(f"Sauvegarde incomplète : {backup / name} est absent")
    return backup


def restore_from_file(service: str, shell_command: str, source: Path) -> None:
    """Envoie un fichier de sauvegarde à une commande de restauration dans un conteneur."""
    with open(source, "rb") as f:              # "rb" = lecture en binaire
        # stdin=f : la commande lit le fichier comme si on le tapait au clavier.
        subprocess.run(compose_exec(service, shell_command), stdin=f, check=True)


def restore_postgres(backup: Path) -> None:
    # On ne peut pas supprimer une base pendant que quelqu'un y est connecté
    # (un service, un script, DBeaver…) : on coupe d'abord ces connexions.
    run_text(
        "postgres",
        'psql -U "$POSTGRES_USER" -d postgres -c '
        "\"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE datname = '$POSTGRES_DB' AND pid <> pg_backend_pid()\"",
    )
    # pg_restore lit la sauvegarde sur son entrée (stdin).
    #   -d postgres     : se connecter d'abord à la base "postgres" (livingdesign va être supprimée)
    #   --clean --create : supprimer la base, la recréer, puis y restaurer le contenu,
    #                     y compris les droits (qui peut se connecter)
    #   --if-exists     : ne pas échouer si la base n'existe plus
    #   --exit-on-error : s'arrêter à la première erreur au lieu de continuer
    # Les rôles (orders_svc…) ne sont pas dans la sauvegarde : ils appartiennent au
    # serveur, pas à la base. Ils existent déjà, créés par db/postgres/init.
    restore_from_file(
        "postgres",
        'pg_restore -U "$POSTGRES_USER" -d postgres --clean --if-exists --create --exit-on-error',
        backup / "postgres.dump",
    )


def restore_mongo(backup: Path) -> None:
    # --drop : supprime chaque collection avant de la restaurer (sinon doublons).
    # --restoreDbUsersAndRoles : recrée l'utilisateur catalog_svc sauvegardé.
    # Le validateur et les index de la collection sont dans l'archive : ils reviennent aussi.
    restore_from_file(
        "mongo",
        'mongorestore --quiet --archive --gzip --drop --restoreDbUsersAndRoles '
        '--db "$MONGO_INITDB_DATABASE" '
        f"{MONGO_AUTH}",
        backup / "mongo.archive.gz",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Restaure une sauvegarde de LivingDesign")
    parser.add_argument("--from", dest="path", help="dossier de la sauvegarde (par défaut : la plus récente)")
    parser.add_argument("--yes", action="store_true", help="ne pas demander de confirmation")
    args = parser.parse_args()

    backup = choose_backup(args.path)
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    print(f"Sauvegarde choisie : {backup.name} (créée le {manifest['created_at']})")

    # Confirmation : une restauration efface les données actuelles.
    if not args.yes:
        answer = input("⚠ Les données actuelles vont être REMPLACÉES. Tape OUI pour continuer : ")
        if answer.strip().upper() != "OUI":   # .upper() met en majuscules : "oui" et "Oui" sont acceptés
            sys.exit("Restauration annulée.")

    print("1. Restauration PostgreSQL (pg_restore)…")
    restore_postgres(backup)
    print("2. Restauration MongoDB (mongorestore)…")
    restore_mongo(backup)

    print("3. Vérification : comparaison avec le manifest…")
    expected, actual = manifest["counts"], count_rows()
    print_counts(actual)
    # Compréhension de dictionnaire : les tables dont le nombre diffère.
    differences = {t: (expected[t], actual.get(t)) for t in expected if actual.get(t) != expected[t]}
    if differences:
        for table, (exp, act) in differences.items():
            print(f"✘ {table} : {act} au lieu de {exp}")
        sys.exit(1)                            # code 1 = échec, utile si un autre outil lance ce script
    print(f"✔ Restauration vérifiée : les {len(expected)} comptages sont identiques à la sauvegarde.")


if __name__ == "__main__":
    main()
