"""Validation structurelle et syntaxique des contrats d'API."""

from pathlib import Path
from graphql import build_schema
import yaml

CONTRACTS_DIR = Path(__file__).resolve().parent.parent / "contracts"


def test_payments_openapi_spec_structure():
    """Verifie que le contrat OpenAPI de payments est valide et complet."""
    spec_path = CONTRACTS_DIR / "openapi" / "payments.yaml"
    assert spec_path.is_file(), "Le fichier payments.yaml est introuvable."

    with open(spec_path, encoding="utf-8") as f:
        spec = yaml.safe_load(f)

    assert spec.get("openapi", "").startswith("3.1"), "OpenAPI doit etre en version 3.1.x"
    assert "info" in spec and "title" in spec["info"]
    assert "paths" in spec

    # Verifie les endpoints fondamentaux
    paths = spec["paths"]
    assert "/payments" in paths
    assert "post" in paths["/payments"]
    assert "/payments/{id}" in paths
    assert "/payments/order/{order_id}" in paths
    assert "/health" in paths

    # Verifie l'entete d'idempotence sur POST /payments
    post_params = paths["/payments"]["post"].get("parameters", [])
    header_names = [p.get("name") for p in post_params if p.get("in") == "header"]
    assert "Idempotency-Key" in header_names

    # Verifie les schemas critiques
    schemas = spec.get("components", {}).get("schemas", {})
    assert "Payment" in schemas
    assert "PaymentStatus" in schemas
    assert "FailureReason" in schemas
    assert "PaymentCreateRequest" in schemas
    assert "ProblemDetails" in schemas


def test_inventory_openapi_spec_structure():
    """Verifie que le contrat OpenAPI de inventory est valide et complet."""
    spec_path = CONTRACTS_DIR / "openapi" / "inventory.yaml"
    assert spec_path.is_file(), "Le fichier inventory.yaml est introuvable."

    with open(spec_path, encoding="utf-8") as f:
        spec = yaml.safe_load(f)

    assert spec.get("openapi", "").startswith("3.1"), "OpenAPI doit etre en version 3.1.x"
    assert "info" in spec and "title" in spec["info"]
    assert "paths" in spec

    # Verifie les endpoints du stock, de la Saga et des entrepots
    paths = spec["paths"]
    assert "/stock/{product_id}" in paths
    assert "/stock/low-stock" in paths
    assert "/reservations" in paths
    assert "post" in paths["/reservations"]
    assert "/reservations/{id}" in paths
    assert "/reservations/order/{order_id}" in paths
    assert "/reservations/{id}/release" in paths
    assert "/reservations/{id}/commit" in paths
    assert "/warehouses" in paths
    assert "/warehouses/fill-rate" in paths
    assert "/health" in paths

    # Verifie les schemas cles de stock et Saga
    schemas = spec.get("components", {}).get("schemas", {})
    assert "ProductStockSummary" in schemas
    assert "LowStockAlert" in schemas
    assert "Reservation" in schemas
    assert "ReservationStatus" in schemas
    assert "ReservationCreateRequest" in schemas
    assert "Warehouse" in schemas
    assert "WarehouseFillRate" in schemas
    assert "ProblemDetails" in schemas


def test_catalog_graphql_schema_structure():
    """Verifie que le schema GraphQL de catalog est syntaxiquement valide et complet."""
    schema_path = CONTRACTS_DIR / "graphql" / "schema.graphql"
    assert schema_path.is_file(), "Le fichier schema.graphql est introuvable."

    schema_content = schema_path.read_text(encoding="utf-8")
    schema = build_schema(schema_content)

    # Verifie la presence des types cles
    type_map = schema.type_map
    assert "Product" in type_map
    assert "Category" in type_map
    assert "ProductStatus" in type_map
    assert "SoldPer" in type_map
    assert "AttributeEntry" in type_map
    assert "ProductPage" in type_map
    assert "ProductFilterInput" in type_map
    assert "CreateProductInput" in type_map

    # Verifie les queries attendues
    query_type = schema.query_type
    assert query_type is not None
    assert "product" in query_type.fields
    assert "products" in query_type.fields
    assert "categories" in query_type.fields
    assert "searchProducts" in query_type.fields

    # Verifie les mutations administratives attendues
    mutation_type = schema.mutation_type
    assert mutation_type is not None
    assert "createProduct" in mutation_type.fields
    assert "updateProductPrice" in mutation_type.fields
    assert "setProductStatus" in mutation_type.fields



