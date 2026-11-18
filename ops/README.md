# ops/ — exploitation

## Sauvegarde et restauration

| Script | Rôle |
|---|---|
| `backup.py`  | Sauvegarde PostgreSQL (`pg_dump`) et MongoDB (`mongodump`) dans `ops/backups/<date>/`, avec un `manifest.json` qui compte les lignes de chaque table |
| `restore.py` | Restaure une sauvegarde (la plus récente par défaut), puis recompte les lignes et les compare au manifest |
| `common.py`  | Fonctions partagées par les deux scripts |

Les outils de sauvegarde tournent **dans les conteneurs** (`docker compose exec`) : rien à installer sur son PC,
et les mots de passe administrateur ne quittent pas les conteneurs. Les sauvegardes contiennent toutes les données :
le dossier `ops/backups/` n'est jamais versionné (`.gitignore`).

```
uv run python ops/backup.py
uv run python ops/restore.py                                   # la plus récente, demande de taper OUI
uv run python ops/restore.py --from ops/backups/2026-11-15_153012
```

**Rétention** : les 7 sauvegardes les plus récentes sont gardées, les plus anciennes sont supprimées à chaque nouvelle sauvegarde.

## Tester la restauration (démonstration pour la soutenance)

Une sauvegarde n'a de valeur que si on sait la restaurer. Le test :

```
uv run python ops/backup.py
docker compose -f infra/docker-compose.yml exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "TRUNCATE orders.orders CASCADE; DROP TABLE payments.payments;"'
uv run python ops/restore.py
```

Après la panne simulée, les commandes et les paiements ont disparu. Après la restauration, le script affiche
`✔ Restauration vérifiée` si chaque table a retrouvé exactement son nombre de lignes.

**Perte totale** (volumes Docker supprimés) : `down -v`, puis `up -d` (les scripts d'init recréent les rôles et
les tables vides), puis `restore.py`.

## Autres dossiers
`architecture/` : schémas d'architecture (composants, flux, déploiement).
