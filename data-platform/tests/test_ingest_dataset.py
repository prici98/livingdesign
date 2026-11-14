"""Tests des fonctions de nettoyage. Lancer : uv run pytest

Chaque cas vient d'un vrai format rencontré dans le dataset IKEA.
"""

import pytest

from ingest_dataset import categorize, parse_measure, parse_price
from livingdesign_commons import Category


def test_prix_simple():
    assert parse_price("$1,380Price $ 1380") == {
        "price_cents": 138000, "previous_price_cents": None, "sold_per": None,
    }


def test_prix_en_promotion():
    result = parse_price("$297Previous price $ 297$237.60Price $ 237.60")
    assert result["price_cents"] == 23760
    assert result["previous_price_cents"] == 29700


def test_prix_par_lot():
    assert parse_price("$6.90/10 piecesPrice $ 6.90/10 pieces")["sold_per"] == {"quantity": 10.0, "unit": "pieces"}


def test_prix_au_kilo_sans_quantite():
    assert parse_price("$9.90/kgPrice $ 9.90/kg")["sold_per"] == {"quantity": 1.0, "unit": "kg"}


def test_prix_illisible():
    assert parse_price("gratuit") is None


# parametrize : le même test, lancé une fois par ligne du tableau.
@pytest.mark.parametrize(("product_type", "expected"), [
    ("table lamp", Category.LUMINAIRES),        # "lamp" doit gagner avant "table"
    ("bed frame", Category.LITS),               # "bed" doit gagner avant "frame"
    ("2-seat modular sofa", Category.CANAPES),
    ("glass door", Category.RANGEMENT),
    ("wine glass", Category.CUISINE),
    ("wash-basin mixer tap", Category.AUTRES),
])
def test_categorize(product_type, expected):
    assert categorize(product_type) == expected


def test_mesure_convertie_en_cm():
    assert parse_measure("Depth", "390 mm") == ("depth_cm", 39)


def test_mesure_illisible():
    assert parse_measure("Area", ":118 /inch²") is None
