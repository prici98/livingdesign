"""Les événements du producteur respectent les contrats de contracts/events/. Lancer : uv run pytest"""

import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data-platform" / "streaming"))   # producer.py n'est pas dans un paquet

from producer import Simulation  # noqa: E402  (import après la ligne précédente, voulu)

EVENTS = ROOT / "contracts" / "events"
PRODUCTS = [
    {"product_id": 1, "price_cents": 4990, "category": "Luminaires", "status": "active"},
    {"product_id": 2, "price_cents": 129900, "category": "Canapés & fauteuils", "status": "active"},
]
STOCK = {
    (1, 1): {"quantity": 50, "reserved": 0, "threshold": 10},
    (2, 2): {"quantity": 3, "reserved": 0, "threshold": 3},
}


def validator(name: str) -> Draft202012Validator:
    schema = json.loads((EVENTS / f"{name}.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)            # le contrat lui-même est un JSON Schema valide
    return Draft202012Validator(schema)


@pytest.fixture
def sim() -> Simulation:
    return Simulation(PRODUCTS, {k: dict(v) for k, v in STOCK.items()})


def test_clics_conformes(sim):
    v = validator("clickstream-event")
    for _ in range(200):
        v.validate(sim.click())                          # lève une erreur au premier écart


def test_commandes_et_stock_conformes(sim):
    orders, stocks = validator("order-created"), validator("stock-updated")
    for _ in range(100):
        order, stock_events = sim.order()
        orders.validate(order)
        for event in stock_events:
            stocks.validate(event)


def test_une_commande_payee_fait_baisser_le_stock(sim):
    before = sum(line["quantity"] for line in sim.stock.values())
    for _ in range(20):
        sim.order()
    assert sum(line["quantity"] for line in sim.stock.values()) < before


def test_le_schema_alerte_est_valide():
    validator("alert")
