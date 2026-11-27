# =============================================================================
#  data-platform/streaming/streaming_job.py — le job Spark Structured Streaming
# =============================================================================
#  Volet 4 du cahier des charges. Ce job lit Kafka en continu et :
#    1. compte les commandes et le chiffre d'affaires par fenêtre d'une minute ;
#    2. compte les vues de pages par catégorie et par minute ;
#    3. lève une alerte LOW_STOCK dès que le stock disponible d'un produit passe
#       sous son seuil, et une alerte ORDER_SPIKE si une minute dépasse un nombre
#       de commandes anormal.
#  Les résultats vont dans le schéma PostgreSQL "analytics" (lu par le tableau de
#  bord) et les alertes aussi dans le topic Kafka livingdesign.alerts.
#
#  Les notions demandées par le sujet, et où elles sont dans ce fichier :
#    • fenêtres de temps   : window("occurred_at", "1 minute")
#    • watermark           : withWatermark("occurred_at", WATERMARK) — un événement
#                            arrivé plus de 2 minutes en retard est ignoré, et Spark
#                            peut oublier les vieilles fenêtres (mémoire bornée)
#    • état                : les compteurs de chaque fenêtre ouverte, gardés entre deux lots
#    • checkpoint          : CHECKPOINT_DIR — Spark y note les positions lues dans
#                            Kafka et l'état. Arrêté puis relancé, il reprend là où il
#                            s'était arrêté.
#    • exactly-once        : Kafka + checkpoint garantissent que chaque lot est
#                            retraité tant qu'il n'est pas validé (au moins une fois) ;
#                            les écritures sont IDEMPOTENTES (même clé = même ligne,
#                            ON CONFLICT) : retraiter un lot ne crée ni perte ni doublon.
#
#  Lancé dans Docker par infra/docker-compose.yml (service spark-streaming).
# =============================================================================

import json
import os
import time

import psycopg
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    ArrayType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

# --- Configuration, lue dans les variables d'environnement (infra/.env) -------
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
TOPICS = {
    "clickstream": "livingdesign.clickstream",
    "orders": "livingdesign.orders",
    "stock": "livingdesign.stock",
    "alerts": "livingdesign.alerts",
}
CHECKPOINT_DIR = os.getenv("CHECKPOINT_DIR", "/checkpoints")
TRIGGER = os.getenv("STREAMING_TRIGGER", "2 seconds")     # un lot toutes les 2 s : alerte en moins de 5 s
WATERMARK = os.getenv("STREAMING_WATERMARK", "2 minutes")
SPIKE_THRESHOLD = int(os.getenv("ORDER_SPIKE_THRESHOLD", "40"))   # commandes par minute
# Mode test : lire des fichiers JSON au lieu de Kafka, sans écrire dans Kafka.
SOURCE_DIR = os.getenv("STREAMING_SOURCE_DIR")             # vide en production

PG_DSN = (
    f"host={os.getenv('POSTGRES_HOST', 'postgres')} port={os.getenv('POSTGRES_INTERNAL_PORT', '5432')} "
    f"dbname={os.getenv('POSTGRES_DB', 'livingdesign')} user=analytics_svc "
    f"password={os.getenv('ANALYTICS_DB_PASSWORD', '')}"
)

# --- Schémas des messages (repris de contracts/events/) -----------------------
# Spark a besoin de connaître la forme du JSON pour le transformer en colonnes.
ORDER_SCHEMA = StructType([
    StructField("event_id", StringType()),
    StructField("occurred_at", TimestampType()),
    StructField("order_id", LongType()),
    StructField("customer_id", LongType()),
    StructField("status", StringType()),
    StructField("total_cents", LongType()),
    StructField("items", ArrayType(StructType([
        StructField("product_id", IntegerType()),
        StructField("quantity", IntegerType()),
        StructField("unit_price_cents", LongType()),
    ]))),
])
STOCK_SCHEMA = StructType([
    StructField("event_id", StringType()),
    StructField("occurred_at", TimestampType()),
    StructField("product_id", IntegerType()),
    StructField("warehouse_id", IntegerType()),
    StructField("quantity", IntegerType()),
    StructField("reserved", IntegerType()),
    StructField("low_stock_threshold", IntegerType()),
])
CLICK_SCHEMA = StructType([
    StructField("event_id", StringType()),
    StructField("occurred_at", TimestampType()),
    StructField("session_id", StringType()),
    StructField("action", StringType()),
    StructField("product_id", IntegerType()),
    StructField("category", StringType()),
])


# =============================================================================
#  Lecture
# =============================================================================
def read_events(spark: SparkSession) -> DataFrame:
    """Un flux unique avec deux colonnes : topic et value (le JSON en texte)."""
    if SOURCE_DIR:   # mode test : fichiers JSON {"topic": …, "value": …}
        schema = StructType([StructField("topic", StringType()), StructField("value", StringType())])
        return spark.readStream.schema(schema).option("maxFilesPerTrigger", 1).json(SOURCE_DIR)
    return (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
        .option("subscribe", ",".join([TOPICS["clickstream"], TOPICS["orders"], TOPICS["stock"]]))
        .option("startingOffsets", "earliest")   # première fois : tout lire ; ensuite le checkpoint décide
        .option("failOnDataLoss", "false")
        .load()
        .select(F.col("topic"), F.col("value").cast("string").alias("value"))   # Kafka livre des octets
    )


def parse(events: DataFrame, topic: str, schema: StructType) -> DataFrame:
    """Garde les messages d'un topic et transforme le JSON en colonnes."""
    return (
        events.filter(F.col("topic") == topic)
        .select(F.from_json("value", schema).alias("e"))   # from_json : texte JSON -> structure
        .select("e.*")                                     # "e.*" : une colonne par champ
        .filter(F.col("occurred_at").isNotNull())          # message illisible : ignoré
    )


# =============================================================================
#  Écritures idempotentes dans PostgreSQL (appelées pour chaque lot)
# =============================================================================
#  foreachBatch donne, à chaque lot, un petit DataFrame ordinaire. Les agrégats
#  sont petits (quelques lignes par minute) : on les rapatrie avec collect() et on
#  les écrit avec psycopg. ON CONFLICT rend chaque écriture rejouable.
def upsert(sql: str, rows: list[tuple]) -> None:
    if not rows:
        return
    with psycopg.connect(PG_DSN) as conn, conn.cursor() as cur:
        cur.executemany(sql, rows)


def write_orders(batch: DataFrame, batch_id: int) -> None:
    rows = [(r.window_start, r.window_end, r.orders, r.paid_orders, r.revenue_cents) for r in batch.collect()]
    upsert(
        """INSERT INTO analytics.orders_per_minute (window_start, window_end, orders, paid_orders, revenue_cents)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (window_start) DO UPDATE SET orders = EXCLUDED.orders, paid_orders = EXCLUDED.paid_orders,
               revenue_cents = EXCLUDED.revenue_cents, updated_at = now()""",
        rows,
    )
    # Pic de commandes : une seule alerte par fenêtre (identifiant = début de fenêtre).
    spikes = [
        {"alert_id": f"ORDER_SPIKE:{r[0].isoformat()}", "alert_type": "ORDER_SPIKE",
         "severity": "WARNING", "product_id": None, "warehouse_id": None,
         "message": f"{r[2]} commandes en une minute (seuil {SPIKE_THRESHOLD})",
         "value": r[2], "threshold": SPIKE_THRESHOLD, "occurred_at": r[0]}
        for r in rows if r[2] >= SPIKE_THRESHOLD
    ]
    save_alerts(batch.sparkSession, spikes)


def write_category_views(batch: DataFrame, batch_id: int) -> None:
    rows = [(r.window_start, r.window_end, r.category, r.views) for r in batch.collect()]
    upsert(
        """INSERT INTO analytics.category_views_per_minute (window_start, window_end, category, views)
           VALUES (%s, %s, %s, %s)
           ON CONFLICT (window_start, category) DO UPDATE SET views = EXCLUDED.views, updated_at = now()""",
        rows,
    )


def write_low_stock(batch: DataFrame, batch_id: int) -> None:
    alerts = [
        {"alert_id": f"LOW_STOCK:{r.event_id}", "alert_type": "LOW_STOCK",
         "severity": "CRITICAL" if r.available <= 0 else "WARNING",
         "product_id": r.product_id, "warehouse_id": r.warehouse_id,
         "message": f"Produit {r.product_id} : {r.available} disponible(s) dans l'entrepôt {r.warehouse_id}",
         "value": r.available, "threshold": r.low_stock_threshold, "occurred_at": r.occurred_at}
        for r in batch.collect()
    ]
    save_alerts(batch.sparkSession, alerts)


def save_alerts(spark: SparkSession, alerts: list[dict]) -> None:
    if not alerts:
        return
    columns = ["alert_id", "alert_type", "severity", "product_id", "warehouse_id",
               "message", "value", "threshold", "occurred_at"]
    upsert(
        f"INSERT INTO analytics.alerts ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))}) "
        "ON CONFLICT (alert_id) DO NOTHING",                    # déjà enregistrée : on ne fait rien
        [tuple(a[c] for c in columns) for a in alerts],
    )
    if SOURCE_DIR:      # mode test : pas de Kafka
        return
    # Publication dans le topic des alertes (le tableau de bord peut s'y abonner).
    # Chaque alerte devient un message : clé = alert_id, valeur = le JSON de contracts/events/alert.schema.json.
    messages = [(a["alert_id"], json.dumps({**a, "occurred_at": a["occurred_at"].isoformat()})) for a in alerts]
    (spark.createDataFrame(messages, "key string, value string")
       .write.format("kafka")
       .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
       .option("topic", TOPICS["alerts"])
       .save())


# =============================================================================
#  Les trois requêtes continues
# =============================================================================
def start_queries(spark: SparkSession) -> list:
    events = read_events(spark)

    # 1. Commandes et chiffre d'affaires par minute ---------------------------
    orders = (
        parse(events, TOPICS["orders"], ORDER_SCHEMA)
        .withWatermark("occurred_at", WATERMARK)           # tolère 2 minutes de retard
        .dropDuplicates(["event_id", "occurred_at"])       # un message reçu deux fois n'est compté qu'une fois
        .groupBy(F.window("occurred_at", "1 minute"))      # fenêtres fixes d'une minute
        .agg(
            F.count("*").alias("orders"),
            F.sum(F.when(F.col("status") == "PAID", 1).otherwise(0)).alias("paid_orders"),
            F.sum(F.when(F.col("status") == "PAID", F.col("total_cents")).otherwise(0)).alias("revenue_cents"),
        )
        .select(F.col("window.start").alias("window_start"), F.col("window.end").alias("window_end"),
                "orders", "paid_orders", "revenue_cents")
    )

    # 2. Vues par catégorie et par minute -------------------------------------
    views = (
        parse(events, TOPICS["clickstream"], CLICK_SCHEMA)
        .filter((F.col("action") == "page_view") & F.col("category").isNotNull())
        .withWatermark("occurred_at", WATERMARK)
        .groupBy(F.window("occurred_at", "1 minute"), "category")
        .agg(F.count("*").alias("views"))
        .select(F.col("window.start").alias("window_start"), F.col("window.end").alias("window_end"),
                "category", "views")
    )

    # 3. Alerte de rupture : chaque mise à jour de stock sous le seuil ---------
    low_stock = (
        parse(events, TOPICS["stock"], STOCK_SCHEMA)
        .withColumn("available", F.col("quantity") - F.col("reserved"))
        .filter(F.col("available") <= F.col("low_stock_threshold"))
    )

    # outputMode "update" : à chaque lot, Spark envoie les fenêtres qui ont changé.
    # Le tableau de bord voit donc la minute en cours se remplir, sans attendre sa fin.
    def start(df: DataFrame, name: str, writer, mode: str):
        return (
            df.writeStream.queryName(name)
            .outputMode(mode)
            .foreachBatch(writer)
            .option("checkpointLocation", f"{CHECKPOINT_DIR}/{name}")   # un checkpoint par requête
            .trigger(processingTime=TRIGGER)
            .start()
        )

    return [
        start(orders, "orders_per_minute", write_orders, "update"),
        start(views, "category_views", write_category_views, "update"),
        start(low_stock, "low_stock_alerts", write_low_stock, "append"),
    ]


def report(queries: list, last_seen: dict) -> None:
    """Toutes les 30 s : événements traités et événements ignorés car trop en retard (watermark)."""
    for q in queries:
        # recentProgress = les derniers lots ; on additionne ceux arrivés depuis le dernier rapport.
        new = [p for p in q.recentProgress if p["batchId"] > last_seen.get(q.name, -1)]
        if not new:
            continue
        last_seen[q.name] = new[-1]["batchId"]
        rows = sum(p["numInputRows"] for p in new)
        dropped = sum(op.get("numRowsDroppedByWatermark", 0) for p in new for op in p.get("stateOperators", []))
        if rows == 0 and dropped == 0:                       # rien de neuf : on n'encombre pas les logs
            continue
        rate = max((p.get("processedRowsPerSecond") or 0) for p in new)
        print(f"[{q.name}] {len(new)} lots, {rows} événements reçus, jusqu'à {rate:.0f}/s traités, "
              f"{dropped} ignorés car trop en retard", flush=True)


def main() -> None:
    spark = (
        SparkSession.builder.appName("livingdesign-streaming")
        .config("spark.sql.shuffle.partitions", "3")        # petit volume : 3 partitions suffisent
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    queries = start_queries(spark)
    print(f"Streaming démarré : {[q.name for q in queries]} (checkpoints dans {CHECKPOINT_DIR})", flush=True)
    last_seen: dict = {}
    while all(q.isActive for q in queries):
        time.sleep(int(os.getenv("STREAMING_REPORT_SECONDS", "30")))
        report(queries, last_seen)
    for q in queries:                                       # une requête s'est arrêtée : on montre pourquoi
        if q.exception():
            raise q.exception()


if __name__ == "__main__":
    main()
