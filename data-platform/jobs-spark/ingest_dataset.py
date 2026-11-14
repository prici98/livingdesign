# =============================================================================
#  LivingDesign — Étape 1 : nettoyer le dataset IKEA
# =============================================================================
#  Entrée  : data-platform/data/raw/furniture_details.csv       (nom, description, prix)
#            data-platform/data/raw/furniture_measurements.csv  (396 colonnes de mesures)
#  Sortie  : data-platform/data/clean/products.jsonl            (un produit propre par ligne)
#            data-platform/data/clean/rejected_products.csv     (les lignes écartées + la raison)
#            data-platform/data/clean/quality_report.json       (les chiffres du nettoyage)
#
#  Lancer (depuis la racine du projet) : python data-platform/jobs-spark/ingest_dataset.py
#
#  Ce job est écrit en pandas pour apprendre. À l'étape Lakehouse, il sera réécrit
#  en PySpark et "raw" / "clean" deviendront les zones raw / curated de MinIO.
# =============================================================================

# --- Imports -----------------------------------------------------------------
# "import" charge une bibliothèque pour pouvoir utiliser ses fonctions.
import json                      
import re                       
from datetime import UTC, datetime  
from pathlib import Path         
import pandas as pd             
from pydantic import ValidationError  

# Notre bibliothèque partagée (libs/livingdesign_commons) : le modèle Product est
# la définition officielle d'un produit, utilisée aussi par MongoDB et l'API catalogue.
from livingdesign_commons import Category, Product


# --- Chemins -----------------------------------------------------------------
JOB_DIR = Path(__file__).resolve().parent        
DATA_DIR = JOB_DIR.parent / "data"                 
RAW_DIR = DATA_DIR / "raw"                      
CLEAN_DIR = DATA_DIR / "clean"
DETAILS_CSV = RAW_DIR / "furniture_details.csv"
MEASUREMENTS_CSV = RAW_DIR / "furniture_measurements.csv"


# =============================================================================
#  1. Lire le fichier des produits et retirer les doublons
# =============================================================================
def load_details():
    df = pd.read_csv(DETAILS_CSV, dtype=str)
    rows_read = len(df)                                   # len() = nombre de lignes
    df = df.drop_duplicates()                             # supprime les lignes 100 % identiques
    exact_duplicates = rows_read - len(df)                # combien on en a retiré

    # Deux lignes peuvent avoir le même uid mais des données différentes : c'est
    # plus grave qu'un doublon exact. On garde la première et on le compte.
    conflicting = df.duplicated(subset="uid", keep="first")   # True pour les uid déjà vus
    uid_conflicts = int(conflicting.sum())                    # True compte pour 1, False pour 0
    df = df[~conflicting]                                     # ~ inverse : on garde les False

    # On renvoie le tableau ET les compteurs (un "tuple" de plusieurs valeurs).
    return df, {"rows_read": rows_read,
                "exact_duplicates_removed": exact_duplicates,
                "uid_conflicts_removed": uid_conflicts}


# =============================================================================
#  2. Décoder la colonne JSON  {"name": ..., "description": ..., "price": ...}
# =============================================================================
def parse_json_column(df: pd.DataFrame):
    records, rejects = [], []             # deux listes vides : lignes valides, lignes rejetées

    # itertuples() parcourt le tableau ligne par ligne ; row.uid et row.data sont les colonnes.
    for row in df.itertuples(index=False):
        try:                              # "try" : on tente quelque chose qui peut échouer…
            data = json.loads(row.data)   # transforme le texte JSON en dictionnaire Python
        except (json.JSONDecodeError, TypeError):   # …et si ça échoue, on arrive ici
            rejects.append({"uid": row.uid, "reason": "json_invalide", "raw": row.data})
            continue                      # passe directement à la ligne suivante

        records.append({
            "source_uid": row.uid,
            # .get(clé, "") renvoie "" si la clé n'existe pas (au lieu de planter)
            # .strip() enlève les espaces au début et à la fin
            "name": (data.get("name") or "").strip(),
            "description": (data.get("description") or "").strip(),
            "price_raw": (data.get("price") or "").strip(),
        })

    return pd.DataFrame(records), rejects   # on reconstruit un tableau à partir de la liste


# =============================================================================
#  3. Comprendre le prix
# =============================================================================
CURRENT_PRICE = re.compile(r"Price \$ ([\d,]+(?:\.\d+)?)(?:/([\d.]+)?\s?([a-zA-Z²]+))?$")
PREVIOUS_PRICE = re.compile(r"Previous price \$ ([\d,]+(?:\.\d+)?)")


def to_cents(amount_text: str) -> int:
    return round(float(amount_text.replace(",", "")) * 100)


def parse_price(price_raw: str):
    match = CURRENT_PRICE.search(price_raw)   
    if match is None:                          
        return None                            

    result = {
        "price_cents": to_cents(match.group(1)), 
        "previous_price_cents": None,
        "sold_per": None,
    }

    previous = PREVIOUS_PRICE.search(price_raw)
    if previous:                                    
        result["previous_price_cents"] = to_cents(previous.group(1))

    if match.group(3):                              
        # "/kg" sans quantité veut dire "pour 1 kg" ; "x or y" renvoie y si x est vide
        quantity = float(match.group(2) or 1)
        result["sold_per"] = {"quantity": quantity, "unit": match.group(3)}

    return result


# =============================================================================
#  4. Déduire la catégorie à partir du type de produit
# =============================================================================
# La description ressemble à "2-seat modular sofa, Samsala dark yellow-green".
# Le TYPE de produit est le morceau avant la première virgule.
#
# Les règles sont testées DANS L'ORDRE et la première qui correspond gagne. L'ordre
# compte : "Table lamp" doit tomber dans Luminaires avant d'atteindre "table", et
# "Bed frame" dans Lits avant d'atteindre "frame" (Décoration).
# Les catégories viennent de l'énumération Category (libs/livingdesign_commons) :
# impossible d'écrire ici une catégorie que le reste du projet ne connaît pas.
# Pour en ajouter une (ex. "Extérieur"), on l'ajoute d'abord dans Category.
CATEGORY_RULES = [
    (Category.LUMINAIRES,          ["lamp", "light", "lighting", "led", "bulb", "shade",
                                    "chandelier", "spotlight"]),
    (Category.CANAPES,             ["sofa", "sofa-bed", "armchair", "chaise longue",
                                    "footstool", "pouffe", "recliner"]),
    (Category.LITS,                ["bed", "bed frame", "bedlinen", "mattress", "duvet",
                                    "duvet cover", "pillow", "pillowcase", "sheet",
                                    "fitted sheet", "headboard", "bedside table", "cot",
                                    "bedspread", "quilt"]),
    (Category.DECORATION,          ["vase", "frame", "picture", "mirror", "plant",
                                    "candle", "flower", "bouquet", "ornament", "clock",
                                    "poster", "decoration"]),
    (Category.TEXTILES,            ["rug", "cushion", "cushion cover", "throw", "curtain",
                                    "blind", "towel", "mat", "door mat", "place mat",
                                    "fabric"]),
    (Category.RANGEMENT,           ["storage", "shelf", "shelves", "shelving unit",
                                    "bookcase", "cabinet", "drawer", "chest", "box",
                                    "organiser", "wardrobe", "tv bench", "tv storage",
                                    "door", "basket", "hook", "rail", "leg", "handle",
                                    "knob", "plinth", "sideboard", "pegboard", "trolley",
                                    "bracket"]),
    (Category.CUISINE,             ["plate", "bowl", "mug", "glass", "cup", "pan",
                                    "saucepan", "frying pan", "knife", "cutlery", "dish",
                                    "jug", "tray", "bottle", "chopping board", "napkin",
                                    "container", "jar", "lid", "serving"]),
    (Category.TABLES,              ["table", "chair", "stool", "bench", "desk"]),
]

COMPILED_RULES = [
    (category, re.compile(r"\b(?:" + "|".join(re.escape(w) for w in words) + r")(?:s|es)?\b"))
    for category, words in CATEGORY_RULES
]

def product_type_of(description: str) -> str:
    # split(",", 1) coupe à la PREMIÈRE virgule seulement → ["2-seat modular sofa", " Samsala…"]
    # [0] prend le premier morceau, .strip() nettoie, .lower() met en minuscules.
    return description.split(",", 1)[0].strip().lower()


def categorize(product_type: str) -> Category:
    for category, pattern in COMPILED_RULES:    
        if pattern.search(product_type):       
            return category                    
    return Category.AUTRES                     

# =============================================================================
#  5. Transformer les 396 colonnes de mesures en attributs propres
# =============================================================================
# Le fichier est "large" : une colonne par mesure, presque toutes vides.
#   uid          | Height | Width | Seat height | … (393 autres)
#   2a302a5b6c67 | 78 cm  | 204 cm| 44 cm       | NaN NaN NaN …
#
# On le passe en format "long" avec melt() : une ligne par mesure réellement remplie.
#   uid          | attribute   | value
#   2a302a5b6c67 | Height      | 78 cm
#   2a302a5b6c67 | Width       | 204 cm
#
# Puis on regroupe par produit pour obtenir un dictionnaire :
#   {"height_cm": 78, "width_cm": 204, "seat_height_cm": 44}
# C'est exactement ce qu'on rangera dans le champ "attributes" de MongoDB.

# Motif d'une valeur : un nombre, des espaces facultatifs, puis l'unité (tout le reste).
VALUE_PATTERN = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*(.*?)\s*$")

# Conversions pour n'avoir qu'une unité par grandeur (sinon "Weight" mélange g et kg).
# unité d'origine -> (unité cible, facteur multiplicateur)
UNIT_CONVERSIONS = {
    "mm": ("cm", 0.1),
    "m":  ("cm", 100),
    "g":  ("kg", 0.001),
    "cl": ("l", 0.01),
    "dl": ("l", 0.1),
    "ml": ("l", 0.001),
}

# Noms d'unités utilisables dans un nom de champ (pas de "²", "/" ou "°" dans une clé).
UNIT_SLUGS = {"m²": "m2", "g/m²": "g_m2", "°": "deg", "hr": "h", "mAh": "mah"}

def snake_case(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def parse_measure(attribute: str, value: str):
    match = VALUE_PATTERN.match(value)
    if match is None:                          
        return None

    number = float(match.group(1))              
    unit = match.group(2)                        

    if unit in UNIT_CONVERSIONS:                 
        unit, factor = UNIT_CONVERSIONS[unit]    
        number = round(number * factor, 4)       
    unit_slug = UNIT_SLUGS.get(unit, unit.lower())  
    key = snake_case(attribute)                      
    if unit_slug:                                    
        key = f"{key}_{unit_slug}"                 

    # Un nombre entier (78.0) est stocké comme entier (78), c'est plus lisible.
    return key, int(number) if number.is_integer() else number


def load_measurements():
    wide = pd.read_csv(MEASUREMENTS_CSV, dtype=str)

    long = wide.melt(id_vars="uid", var_name="attribute", value_name="value")
    long = long.dropna(subset=["value"])        

    attributes_by_uid = {}                      
    unreadable = []                            

    for row in long.itertuples(index=False):
        parsed = parse_measure(row.attribute, row.value)
        if parsed is None:
            unreadable.append({"uid": row.uid, "attribute": row.attribute, "value": row.value})
            continue
        key, number = parsed
        # setdefault crée un dictionnaire vide pour ce uid s'il n'existe pas encore
        attrs = attributes_by_uid.setdefault(row.uid, {})
        # "Weight" et "Weight." donnent la même clé : on garde la première valeur trouvée
        attrs.setdefault(key, number)

    stats = {
        "measurement_rows": len(wide),
        "measurement_rows_all_empty": len(wide) - len(attributes_by_uid),
        "measures_read": len(long),
        "measures_unreadable": len(unreadable),
    }
    return attributes_by_uid, unreadable, stats


# =============================================================================
#  6. Assembler, contrôler la qualité, numéroter
# =============================================================================
def build_products(records: pd.DataFrame, attributes_by_uid: dict):
    candidates, rejects = [], []

    for row in records.itertuples(index=False):
        price = parse_price(row.price_raw)
        if price is None:                                  # le prix n'a pas pu être lu
            rejects.append({"uid": row.source_uid, "reason": "prix_illisible", "raw": row.price_raw})
            continue

        product_type = product_type_of(row.description)
        candidates.append({
            "source_uid": row.source_uid,             
            "name": row.name,                         
            "product_type": product_type,             
            "description": row.description,
            "category": categorize(product_type),
            "price_cents": price["price_cents"],
            "previous_price_cents": price["previous_price_cents"],
            "sold_per": price["sold_per"],
            "status": "active",
            # .get(uid, {}) : un produit sans mesures reçoit un dictionnaire vide
            "attributes": attributes_by_uid.get(row.source_uid, {}),
        })

    # --- Validation Pydantic et numérotation ---
   
    candidates.sort(key=lambda c: c["source_uid"])  

    products = []
    next_id = 1                                    
    for candidate in candidates:
        try:
            # Product(...) vérifie TOUT ce que décrit le modèle : nom et description
            # non vides, prix > 0, catégorie connue, ancien prix > prix actuel…
            # "**candidate" passe chaque clé du dictionnaire comme argument nommé.
            product = Product(product_id=next_id, **candidate)
        except ValidationError as error:
            fields = sorted({str(e["loc"][0]) for e in error.errors()})   
            rejects.append({"uid": candidate["source_uid"],
                            "reason": "invalide:" + ",".join(fields),
                            "raw": candidate["description"]})
            continue                               
        products.append(product.model_dump(mode="json"))
        next_id += 1

    return products, rejects


# =============================================================================
#  7. Écrire les résultats
# =============================================================================
def write_outputs(products, rejects, report):
    # parents=True crée aussi les dossiers parents ; exist_ok=True : pas d'erreur s'il existe
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)

    # JSONL = un objet JSON par ligne. Avantages : on peut lire le fichier ligne par
    # ligne sans tout charger en mémoire, et mongoimport le comprend directement.
    # "with" ferme le fichier automatiquement, même en cas d'erreur.
    with open(CLEAN_DIR / "products.jsonl", "w", encoding="utf-8") as f:
        for product in products:
            f.write(json.dumps(product, ensure_ascii=False) + "\n")

    pd.DataFrame(rejects, columns=["uid", "reason", "raw"]).to_csv(
        CLEAN_DIR / "rejected_products.csv", index=False, encoding="utf-8")

    with open(CLEAN_DIR / "quality_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)   # indent=2 : joliment indenté


# =============================================================================
#  Programme principal : on enchaîne les étapes dans l'ordre
# =============================================================================
def main():
    print("1. Lecture des produits…")
    details, dedup_stats = load_details()

    print("2. Décodage du JSON…")
    records, json_rejects = parse_json_column(details)

    print("3. Lecture des mesures…")
    attributes_by_uid, unreadable, measure_stats = load_measurements()

    print("4. Prix, catégories, contrôles qualité, numérotation…")
    products, quality_rejects = build_products(records, attributes_by_uid)
    rejects = json_rejects + quality_rejects         

    df = pd.DataFrame(products)                      
    product_uids = set(df["source_uid"])             
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        **dedup_stats,
        **measure_stats,
        "products_kept": len(products),
        "products_rejected": len(rejects),
        # value_counts compte les occurrences ; to_dict le transforme en dictionnaire
        "rejects_by_reason": pd.Series([r["reason"] for r in rejects], dtype=str).value_counts().to_dict(),
        "products_by_category": df["category"].value_counts().to_dict(),
        "products_on_promotion": int(df["previous_price_cents"].notna().sum()),
        "products_sold_per_unit": int(df["sold_per"].notna().sum()),
        "products_without_measures": int((df["attributes"].map(len) == 0).sum()),
        "measurements_without_product": len(set(attributes_by_uid) - product_uids),
        # Les 15 types non classés les plus fréquents : pour améliorer CATEGORY_RULES
        "top_unclassified_types": df.loc[df["category"] == "Autres", "product_type"]
                                    .value_counts().head(15).to_dict(),
        "price_eur": {
            "min": df["price_cents"].min() / 100,
            "median": df["price_cents"].median() / 100,
            "max": df["price_cents"].max() / 100,
            "share_above_200": round(float((df["price_cents"] > 20_000).mean()), 3),
        },
    }
    # Les valeurs numpy (int64…) ne passent pas en JSON : on les convertit en types Python.
    report = json.loads(json.dumps(report, default=lambda v: v.item()))

    print("5. Écriture des fichiers…")
    write_outputs(products, rejects, report)

    print()
    print(f"   Lignes lues          : {report['rows_read']}")
    print(f"   Doublons retirés     : {report['exact_duplicates_removed']}")
    print(f"   Produits gardés      : {report['products_kept']}")
    print(f"   Produits rejetés     : {report['products_rejected']}  {report['rejects_by_reason']}")
    print(f"   En promotion         : {report['products_on_promotion']}")
    print(f"   Sans mesures         : {report['products_without_measures']}")
    print("   Par catégorie        :")
    for category, count in report["products_by_category"].items():
        print(f"      {category:<28} {count:>5}")   # :<28 aligne à gauche sur 28 caractères
    print(f"\n   Résultats dans {CLEAN_DIR}")


if __name__ == "__main__":
    main()
