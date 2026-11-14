# =============================================================================
#  LivingDesign — Étape 2a : charger le catalogue propre dans MongoDB
# =============================================================================

from datetime import UTC, datetime           
from pathlib import Path                     
from urllib.parse import quote_plus          
from pydantic import ValidationError          
from pymongo import MongoClient, ReplaceOne   
from pymongo.errors import BulkWriteError    

from livingdesign_commons import Product, get_settings  

# Ce fichier est dans db/mongo/seed/. parents[0] = seed, [1] = mongo, [2] = db,
# [3] = la racine du projet. On part de la racine pour trouver les autres dossiers.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
PRODUCTS_FILE = PROJECT_ROOT / "data-platform" / "data" / "clean" / "products.jsonl"

settings = get_settings()

# =============================================================================
#  1. Se connecter à MongoDB avec l'utilisateur du service catalogue
# =============================================================================
def connect():
    db_name = settings.mongo_db
   
    password = quote_plus(settings.catalog_db_password.get_secret_value())

    # Format d'une URL MongoDB : mongodb://utilisateur:motdepasse@hôte:port/base
    # "localhost" = ton PC ; docker-compose y a publié le port du conteneur.
    uri = f"mongodb://catalog_svc:{password}@{settings.mongo_host}:{settings.mongo_port}/{db_name}"

    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")                       # vérifie tout de suite la connexion
    return client, client[db_name]["catalog"]          # client[base][collection]


# =============================================================================
#  2. Lire les produits nettoyés
# =============================================================================
def read_products():
    if not PRODUCTS_FILE.exists():                    
        raise SystemExit(f"Fichier introuvable : {PRODUCTS_FILE}\n"
                         "Lance d'abord : python data-platform/jobs-spark/ingest_dataset.py")   

    now = datetime.now(UTC)
    products = []
    with open(PRODUCTS_FILE, encoding="utf-8") as f:
        # enumerate(f, start=1) donne aussi le numéro de ligne, utile en cas d'erreur.
        for line_number, line in enumerate(f, start=1):
            try:
                # model_validate_json lit ET vérifie la ligne JSON en une seule étape.
                product = Product.model_validate_json(line)
            except ValidationError as error:
                raise SystemExit(f"Ligne {line_number} invalide :\n{error}") from error
            document = product.model_dump(mode="json")  
            document["indexed_at"] = now                
    return products


# =============================================================================
#  3. Écrire en "upsert" : mettre à jour si le produit existe, sinon l'insérer
# =============================================================================
def load(collection, products):
    # On prépare une liste d'opérations, envoyées ensuite en UNE seule fois
    # (bulk_write) : beaucoup plus rapide que 7 736 allers-retours avec la base.
    operations = [
        ReplaceOne(
            {"product_id": p["product_id"]}, 
            p,                              
            upsert=True,                     
        )
        for p in products
    ]

    try:
        result = collection.bulk_write(operations, ordered=False)
    except BulkWriteError as error:
        details = error.details["writeErrors"]
        print(f"✘ {len(details)} document(s) refusé(s) par le validateur. Exemples :")
        for e in details[:3]:
            print("   ", e.get("errmsg"))
        raise SystemExit(1) from error

    print(f"✔ {result.upserted_count} produits insérés, {result.modified_count} mis à jour")


# =============================================================================
#  4. Vérifier : quelques requêtes pour voir que tout est là
# =============================================================================
def verify(collection):
    print(f"✔ Documents dans catalog : {collection.count_documents({})}")   # {} = aucun filtre

    # Pipeline d'agrégation : l'équivalent de "SELECT category, COUNT(*) … GROUP BY".
    # Chaque étape transforme le résultat de la précédente.
    pipeline = [
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},   
        {"$sort": {"count": -1}},                                
    ]
    print("  Par catégorie :")
    for row in collection.aggregate(pipeline):
        print(f"     {row['_id']:<28} {row['count']:>5}")

    hits = collection.count_documents({"$text": {"$search": "sofa"}})
    print(f"  Recherche « sofa »   : {hits} résultats")

    tall_seats = collection.count_documents({"attributes.seat_height_cm": {"$gte": 45}})
    print(f"  Assise ≥ 45 cm       : {tall_seats} produits")


def main():
    client, collection = connect()
    products = read_products()
    print(f"{len(products)} produits lus dans {PRODUCTS_FILE.name}")
    load(collection, products)
    verify(collection)
    client.close()                            


if __name__ == "__main__":
    main()
