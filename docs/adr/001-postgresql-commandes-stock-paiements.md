# ADR-001 — PostgreSQL pour les commandes, le stock et les paiements
**Statut** : acceptée

## Contexte
Une commande LivingDesign touche un client, des lignes, une réservation de stock et un paiement.
Une erreur coûte de l'argent : vendre un canapé qui n'est plus en stock, débiter deux fois une carte.

## Options étudiées
| Option | Points forts | Points faibles |
|---|---|---|
| **PostgreSQL** | Transactions ACID, clés étrangères, CHECK, partitionnement, EXPLAIN | Montée en charge d'abord verticale |
| MongoDB | Schéma souple, scalabilité horizontale | Pas de clé étrangère, transactions multi-documents plus lourdes |
| Cassandra | Écritures massives, très disponible | Cohérence éventuelle, pas de transaction |

## Décision
PostgreSQL 16. Au sens du théorème CAP, on privilégie la **cohérence** : mieux vaut refuser une commande qu'enregistrer un état faux.
Un seul serveur, **un schéma et un rôle par microservice** (`orders_svc`, `inventory_svc`, `payments_svc`, `auth_svc`).

Choix de modélisation :
- `inventory.stock` a pour clé `(product_id, warehouse_id)` : un produit peut être dans plusieurs entrepôts.
- `reserved` + table `reservations` : réserver et libérer du stock est idempotent (base de la Saga).
- Base : le script SQL fourni pour le projet. Les ajouts et modifications exigés par le cahier des charges sont dans le même fichier (`db/postgres/init/01_init_livingdesign.sql`), signalés par `[+]` avec leur raison.
- Partitionnement de `orders.orders` par mois : prévu à l'étape 3, comme migration mesurée avec EXPLAIN.
- Montants en centimes entiers : aucune erreur d'arrondi.
- La règle « paiement refusé au-dessus de 3 000 € » vit dans le code du payment-service, pas dans la base : c'est une règle métier qui peut changer.

## Conséquences
- (+) La base garantit l'intégrité : FK, CHECK (quantités ≥ 0, réservé ≤ stock), statuts limités.
- (−) Aucune FK entre schémas ni vers MongoDB : `product_id` et `order_id` sont des liens applicatifs, vérifiés par les services via les API.
