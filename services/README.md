# services/ — les microservices de LivingDesign

| Service | Rôle | Base | Port |
|---|---|---|---|
| `catalog/`   | Catalogue produits, API GraphQL | MongoDB `catalog` | 8004 |
| `inventory/` | Stock, entrepôts, réservations | PostgreSQL `inventory` | 8002 |
| `orders/`    | Commandes, orchestre la Saga | PostgreSQL `orders` | 8001 |
| `payments/`  | Paiements idempotents (refus > 3 000 €) | PostgreSQL `payments` | 8003 |
| `auth/`      | Connexion, JWT, rôles (bonus) | PostgreSQL `auth` | 8005 |

Chaque service a la même forme :

```
<service>/
├── app/
│   ├── api/           routes HTTP (REST) ou résolveurs GraphQL : la porte d'entrée
│   ├── schemas/       formats des données échangées par l'API (validation des entrées/sorties)
│   ├── services/      logique applicative : enchaîne les étapes d'un cas d'usage
│   ├── repositories/  accès à la base : les requêtes SQL / MongoDB, et rien d'autre
│   ├── models/        tables ou documents tels qu'ils sont stockés
│   ├── domain/        règles métier pures (ex. « refus au-dessus de 3 000 € »), sans base ni HTTP
│   ├── clients/       appels vers les AUTRES services (timeout, retry, circuit breaker)
│   ├── events/        messages Kafka publiés ou consommés
│   ├── core/          configuration, journaux, sécurité
│   └── db/            connexion et sessions de base de données
├── migrations/        évolutions du schéma après la création initiale (db/postgres/init)
├── tests/             tests unitaires et tests d'API du service
└── Dockerfile         l'image Docker du service
```

Le chemin d'une requête : `api` → `schemas` (validation) → `services` → `domain` (règles) → `repositories` → `db`.
