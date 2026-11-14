# Travailler à deux sur LivingDesign

## Les règles du jeu

1. **`main` est toujours stable.** Personne ne pousse directement dessus : tout passe par une *pull request* (PR) relue par l'autre.
2. **Une branche par tâche**, préfixée par son prénom : `prici/etape3-explain`, `alex/catalog-graphql`. Une branche vit quelques jours, pas tout le projet.
3. **On fusionne souvent** (au moins à chaque étape terminée). Plus une branche vit longtemps, plus les conflits sont gros.
4. **On se répartit par dossiers** pour éviter de modifier les mêmes fichiers en même temps (voir plus bas).

## Le cycle d'une tâche

```bash
# 1. Partir d'un main à jour
git switch main
git pull

# 2. Créer sa branche
git switch -c prici/etape3-explain

# 3. Travailler, puis enregistrer par petites étapes
git add .
git commit -m "feat(db): ajoute les mesures EXPLAIN avant index"

# 4. Vérifier avant de partager
uv run ruff check .
uv run pytest

# 5. Envoyer la branche sur GitHub (le -u seulement la première fois)
git push -u origin prici/etape3-explain
```

6. Sur GitHub : **Compare & pull request**, remplir le modèle, demander la relecture de l'autre.
7. L'autre relit, commente, approuve. La CI doit être verte. On clique **Merge**.
8. Chacun remet son `main` à jour : `git switch main` puis `git pull`. On supprime la branche : `git branch -d prici/etape3-explain`.

**Récupérer le travail de l'autre** pendant qu'on est sur sa branche :

```bash
git fetch
git merge origin/main
```

## Messages de commit

Format : `type(zone): description à l'infinitif ou au présent`.

| Type | Quand |
|---|---|
| `feat` | nouvelle fonctionnalité |
| `fix` | correction de bug |
| `docs` | documentation, ADR |
| `test` | ajout ou modification de tests |
| `refactor` | réorganisation sans changer le comportement |
| `chore` | configuration, dépendances, outillage |

Exemples : `feat(inventory): route POST /stock/reserve`, `fix(ingest): accepte les prix au m²`, `docs(adr): ADR-003 choix de Kafka`.

## Les dépendances avec uv

```bash
uv add httpx                                    # ajoute une bibliothèque aux scripts de la racine
uv add --package livingdesign-commons httpx     # l'ajoute à la bibliothèque partagée
uv add --dev mypy                               # outil de développement uniquement
uv remove httpx                                 # retire une bibliothèque
uv sync                                         # après un git pull : met son .venv à jour
```

`uv add` modifie `pyproject.toml` **et** `uv.lock` : on committe toujours les deux ensemble.

**Conflit sur `uv.lock`** (vous avez tous les deux ajouté une dépendance) : ne pas le corriger à la main.
Garder la version de `main` (`git checkout --theirs uv.lock` pendant un merge de `origin/main`), puis lancer `uv lock` pour le régénérer et committer.

## Qui fait quoi (proposition, à ajuster)

| Personne A | Personne B |
|---|---|
| `db/`, `ops/` (EXPLAIN, partitionnement, sauvegardes) | `contracts/`, `libs/` (contrats d'API, modèles Pydantic) |
| `services/inventory`, `services/payments` | `services/catalog`, `services/orders` |
| `data-platform/streaming`, `infra/kafka` | `data-platform/lakehouse`, `infra/minio` |

Les fichiers partagés (`pyproject.toml`, `uv.lock`, `infra/docker-compose.yml`, `libs/`) : on prévient l'autre avant de les modifier.

## Ce qui ne va jamais sur GitHub
- `infra/.env` : chacun a le sien, copié depuis `infra/.env.example`.
- `data-platform/data/` : chacun télécharge le dataset Kaggle et le place dans `data-platform/data/raw/`.
- `.venv/` : chacun le recrée avec `uv sync`.
Le fichier `.gitignore` s'en charge ; vérifiez quand même avec `git status` avant chaque commit.
