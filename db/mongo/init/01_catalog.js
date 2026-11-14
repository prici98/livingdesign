// =============================================================================
//  01 — MongoDB : base "livingdesign", collection "catalog"
// =============================================================================
const dbName = process.env.MONGO_INITDB_DATABASE || "livingdesign";

const ld = db.getSiblingDB(dbName);

// ---------------------------------------------------------------- utilisateur
// Le service catalogue se connectera avec cet utilisateur, qui ne peut lire et
// écrire QUE dans la base livingdesign (principe du moindre privilège).
ld.createUser({
  user: "catalog_svc",
  pwd: process.env.CATALOG_DB_PASSWORD,
  roles: [{ role: "readWrite", db: dbName }],
});

// ---------------------------------------------------------------- collection
// MongoDB accepte n'importe quel document par défaut. On ajoute un VALIDATEUR :
// les champs communs à tous les produits sont contrôlés, mais "attributes" reste
// libre, car un canapé et une lampe n'ont pas les mêmes mesures.
ld.createCollection("catalog", {
  validator: {
    $jsonSchema: {                        
      required: ["product_id", "name", "category", "price_cents", "status"],  
      properties: {
        product_id:           { bsonType: "int", minimum: 1 },   
        source_uid:           { bsonType: "string" },
        name:                 { bsonType: "string", minLength: 1 }, 
        product_type:         { bsonType: "string" },
        description:          { bsonType: "string" },
        category:             { bsonType: "string" },
        price_cents:          { bsonType: "int", minimum: 0 },
        previous_price_cents: { bsonType: ["int", "null"] },     
        sold_per:             { bsonType: ["object", "null"] },
        status:               { enum: ["active", "inactive"] },   
        attributes:           { bsonType: "object" },               
        indexed_at:           { bsonType: "date" },
      },
    },
  },
  validationLevel: "strict",             
  validationAction: "error",               
});

// ---------------------------------------------------------------- index
// 1 = ordre croissant. unique: true = deux produits ne peuvent pas avoir le même product_id.
ld.catalog.createIndex({ product_id: 1 }, { unique: true, name: "uq_product_id" });

// Index composé : filtrer par catégorie puis par statut (la page « Canapés actifs »).
ld.catalog.createIndex({ category: 1, status: 1 }, { name: "idx_category_status" });

// Index texte : la barre de recherche. weights = le nom compte 3 fois plus que la description.
ld.catalog.createIndex(
  { name: "text", product_type: "text", description: "text" },
  { name: "txt_search", weights: { name: 3, product_type: 3, description: 1 }, default_language: "english" }
);

print("catalog : utilisateur, validateur et index créés");
