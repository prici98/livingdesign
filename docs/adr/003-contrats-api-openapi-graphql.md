# ADR-003 — Approche Contract-First et dualite OpenAPI / GraphQL
**Statut** : acceptée

## Contexte
LivingDesign est compose de microservices communicant sur le reseau. Deux defis majeurs se posent :
1. Le travail en binome et la parallelisation du developpement exigent une frontiere stable et independante de l'implementation des services.
2. Les services n'ont pas les memes besoins d'interrogation :
   - Le catalogue produit presente une grande variabilite d'attributs meubles (ADR-002) et des modes de consultation varies (listing, recherche textuelle, fiche produit detaillee).
   - Les services de paiement et de stock necessitent des transactions deterministes, verifiables et fortement contraintes (idempotence, Saga).

## Options etudiees
| Option | Points forts | Points faibles |
|---|---|---|
| **Code-First tout-REST** (FastAPI genere Swagger) | Simple et rapide a initialiser | Fort couplage au code Python, developpement en binome bloque tant que le service n'est pas code, surconsommation de bande passante sur le catalogue (over-fetching) |
| **Tout-GraphQL** (tous les microservices en GraphQL) | Un seul protocole pour toute l'architecture | Difficile a cacher au niveau HTTP Gateway, complexite inutile pour des operations transactionnelles unitaires simples (debiter un paiement, liberer un stock) |
| **Contract-First bimodal : OpenAPI 3.1 + GraphQL SDL** | Contrats ecrits avant le code, chaque protocole est aligne sur son cas d'usage optimal, generation de tests et de mocks des le debut | Deux technologies d'API a maintenir dans le depot |

## Decision
Nous adoptons l'approche **Contract-First** avec une repartition bimodale :

1. **GraphQL SDL pour le catalogue (`catalog-service`, port 8004)** :
   - Schema : `contracts/graphql/schema.graphql`.
   - Permet aux clients de selectionner exactement les champs necessaires (reduction drastique de l'over-fetching sur les pages de listing).
   - Encapsule les attributs dimensionnels dynamiques de MongoDB via le type `AttributeEntry` et le scalaire `JSON`.
   - Aligne sur l'enum `Category` de la librairie partagée `livingdesign_commons`.

2. **OpenAPI 3.1 pour les services transactionnels (`payments`, `inventory`, `orders`, `auth`)** :
   - Schemas : `contracts/openapi/payments.yaml` et `contracts/openapi/inventory.yaml`.
   - Conforme au standard HTTP REST et JSON Schema 2020-12.
   - Versioning explicite des routes avec prefixe `/v1/` (`/v1/payments`, `/v1/stock/{product_id}`, etc.).
   - Declaration formelle de la securite et du RBAC via `securitySchemes` :
     - `BearerAuth` (JWT) pour les utilisateurs applicatifs (`admin`, `logistics`, `analyst`, `catalog_manager`).
     - `ApiKeyAuth` (`X-API-Key`) pour les echanges machine-to-machine inter-services (`service_account`).
     - Reponses d'erreur standardisees `401 Unauthorized` et `403 Forbidden`.
   - Idempotence bancaire standardisee via le header IETF `Idempotency-Key` (UUID v4).
   - Format d'erreur normalise sur la RFC 9457 (`application/problem+json`).
   - Prise en charge native du pattern Saga dans `inventory` (`POST /v1/reservations`, `/commit`, `/release`).

3. **Validation automatique dans la suite de tests** :
   - Le fichier `tests/test_contracts.py` analyse la syntaxe et l'AST des contrats a l'aide de PyYAML et `graphql-core` avant tout deploiement ou ecriture de code metier.

## Consequences
- (+) Travail en binome totalement deconnecte : le consommateur peut coder ses clients HTTP/GraphQL des aujourd'hui sans attendre l'implementation serveur.
- (+) Garantie contractuelle stricte contre les regressions et les erreurs d'arrondi (montants toujours en centimes entiers).
- (+) Traitement normalise des erreurs via Problem Details (RFC 9457).
- (−) Necessite de maintenir synchronises les schemas de contrats avec le code des schemas Pydantic lors des evolutions futures (garanti par les tests automatises).

