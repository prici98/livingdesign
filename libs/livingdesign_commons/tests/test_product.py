"""Tests du modèle Product. Lancer : uv run pytest"""

import pytest
from pydantic import ValidationError

from livingdesign_commons import Category, Product

# Un produit valide, réutilisé et modifié dans chaque test.
VALID = {
    "product_id": 1,
    "source_uid": "000e1ea960ac",
    "name": "KALLAX",
    "product_type": "shelving unit",
    "description": "Shelving unit, white, 77x147 cm",
    "category": "Rangement",
    "price_cents": 14900,
}


def test_un_produit_valide_est_accepte():
    product = Product.model_validate(VALID)
    assert product.category is Category.RANGEMENT    
    assert product.status == "active"                   
    assert product.attributes == {}


def test_un_prix_negatif_est_refuse():
    with pytest.raises(ValidationError):                
        Product.model_validate({**VALID, "price_cents": -100})


def test_une_categorie_inconnue_est_refusee():
    with pytest.raises(ValidationError):
        Product.model_validate({**VALID, "category": "Jardin"})


def test_un_champ_inconnu_est_refuse():
    with pytest.raises(ValidationError):
        Product.model_validate({**VALID, "prix": 10})  


def test_l_ancien_prix_doit_etre_plus_eleve():
    with pytest.raises(ValidationError, match="previous_price_cents"):
        Product.model_validate({**VALID, "previous_price_cents": 10000})


def test_aller_retour_json():
    product = Product.model_validate({**VALID, "sold_per": {"quantity": 10, "unit": "pieces"}})
    copy = Product.model_validate_json(product.model_dump_json())   # objet -> JSON -> objet
    assert copy == product
