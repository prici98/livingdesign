# contracts/ — les contrats, écrits AVANT le code
- `openapi/` : description des API REST (orders, inventory, payments, auth) au format OpenAPI 3
- `graphql/` : schéma GraphQL du catalogue (`schema.graphql`)
- `events/`  : format des messages Kafka (JSON Schema), ex. `clickstream-event`, `order-created`

Un contrat est la frontière entre deux services : chacun peut évoluer tant qu'il le respecte.
