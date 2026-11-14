"""Bibliothèque partagée de LivingDesign.

Usage :
    from livingdesign_commons import Product, Category, get_settings
"""

from livingdesign_commons.models.product import Category, Product, SoldPer
from livingdesign_commons.settings import Settings, get_settings

# __all__ = la liste de ce que "from livingdesign_commons import *" exporte.
__all__ = ["Category", "Product", "SoldPer", "Settings", "get_settings"]
