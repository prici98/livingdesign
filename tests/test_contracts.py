"""Validation structurelle et syntaxique des contrats d'API."""

from pathlib import Path
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
