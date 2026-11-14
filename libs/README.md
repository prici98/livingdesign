# libs/ — code partagé

`livingdesign_commons/` est une bibliothèque Python du workspace uv, importée partout :

```python
from livingdesign_commons import Product, Category, get_settings
```

- `models/product.py` : le modèle Pydantic `Product`, la définition officielle d'un produit
  (utilisée par le nettoyage, le chargement MongoDB et, plus tard, l'API catalogue)
- `settings.py` : la configuration lue et vérifiée par Pydantic depuis `infra/.env`
- `tests/` : les tests de la bibliothèque (`uv run pytest`)

Plus tard : vérification du JWT, format des journaux, identifiant de corrélation, client HTTP résilient.
Rien de métier propre à un seul service ici.
