# =============================================================================
#  Le modèle Pydantic d'un produit du catalogue
# =============================================================================
from enum import StrEnum                     
from typing import Literal                  

from pydantic import (
    BaseModel,                             
    ConfigDict,                             
    Field,                                   
    PositiveFloat,                          
    PositiveInt,                             
    model_validator,                        
)


class Category(StrEnum):
    """Les catégories du site. Ajouter une catégorie = l'ajouter ICI d'abord."""

    LUMINAIRES = "Luminaires"
    CANAPES = "Canapés & fauteuils"
    LITS = "Lits & literie"
    DECORATION = "Décoration"
    TEXTILES = "Textiles"
    RANGEMENT = "Rangement"
    CUISINE = "Cuisine & arts de la table"
    TABLES = "Tables & chaises"
    AUTRES = "Autres"


class SoldPer(BaseModel):
    """Vente par lot ou à l'unité de mesure : "6,90 € les 10 pièces", "9,90 € le kg"."""

    model_config = ConfigDict(extra="forbid")    

    quantity: PositiveFloat                       
    unit: str = Field(min_length=1)             


class Product(BaseModel):
    """Un produit du catalogue LivingDesign, tel qu'il est stocké dans MongoDB."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

  
    product_id: PositiveInt                     
    source_uid: str = Field(min_length=1)         
    name: str = Field(min_length=1)              
    product_type: str = Field(min_length=1)       
    description: str = Field(min_length=1)
    category: Category                           
    price_cents: PositiveInt                      
    previous_price_cents: PositiveInt | None = None
    sold_per: SoldPer | None = None               
    status: Literal["active", "inactive"] = "active"
   
    attributes: dict[str, int | float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def previous_price_must_be_higher(self) -> "Product":
        if self.previous_price_cents is not None and self.previous_price_cents <= self.price_cents:
            raise ValueError("previous_price_cents doit être supérieur à price_cents")
        return self                             
