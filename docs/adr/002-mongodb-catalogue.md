# ADR-002 — MongoDB pour le catalogue
**Statut** : acceptée

## Contexte
Le dataset IKEA décrit les mesures dans 396 colonnes, mais chaque produit n'en remplit que 2 ou 3 en moyenne :
une lampe a une puissance, un canapé une hauteur d'assise, un tapis une épaisseur de poils.
Le catalogue est surtout lu ; un prix modifié peut apparaître avec quelques secondes de retard.

## Options étudiées
| Option | Points forts | Points faibles |
|---|---|---|
| **MongoDB** | Documents de forme variable, index texte, validateur JSON Schema | Pas de lien vérifié avec PostgreSQL |
| Table SQL à 396 colonnes | Tout en relationnel | 99 % de cases vides, une migration par nouvelle mesure |
| PostgreSQL + JSONB | Une seule technologie | Mélange les responsabilités des services |

## Décision
MongoDB 7, collection `catalog`, utilisateur `catalog_svc` limité à sa base.
Validateur `$jsonSchema` sur les champs communs (`product_id`, `name`, `category`, `price_cents`, `status`) ; `attributes` reste libre.
Index : unique sur `product_id`, `(category, status)`, texte sur nom, type et description.

## Conséquences
- (+) Ajouter une catégorie ou une mesure ne demande aucune migration.
- (−) Le lien `product_id` avec PostgreSQL n'est garanti par aucune base : le service Commandes vérifie le produit et son prix via l'API du catalogue.
- Les prix du dataset sont en dollars ; LivingDesign les affiche en euros au même montant (projet fictif).
