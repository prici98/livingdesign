# db/ — création et remplissage des bases

| Dossier | Contenu | Quand |
|---|---|---|
| `postgres/init/` | `01_init_livingdesign.sql` : rôles, schémas, tables, index et vues (script fourni + compléments marqués `[+]`) | automatiquement, au 1er démarrage de PostgreSQL |
| `postgres/seed/` | `generate_fake_data.py` : entrepôts, stock, clients, commandes, paiements fictifs | à la main, après le démarrage |
| `mongo/init/`    | `01_catalog.js` : utilisateur, validateur, index | automatiquement, au 1er démarrage de MongoDB |
| `mongo/seed/`    | `load_catalog.py` : charge le catalogue nettoyé | à la main, après le démarrage |

Les scripts `init` ne tournent que sur une base vide : après une modification,
`docker compose -f infra/docker-compose.yml down -v` puis `up -d`.
