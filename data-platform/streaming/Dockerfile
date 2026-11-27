# Image du job Spark Structured Streaming.
# Base : l'image officielle Spark 3.5.8 avec Java 17 et Python 3.
FROM spark:3.5.8-java17-python3

USER root
# psycopg : pour écrire les résultats dans PostgreSQL (schéma analytics).
# PIP_BREAK_SYSTEM_PACKAGES : autorise pip à installer dans le Python du système (image dédiée).
ENV PIP_BREAK_SYSTEM_PACKAGES=1
RUN pip install --no-cache-dir "psycopg[binary]==3.2.3"

WORKDIR /app
COPY streaming_job.py /app/streaming_job.py

# --packages télécharge le connecteur Kafka de Spark au démarrage (même version que Spark).
# spark.jars.ivy : dossier où le ranger.
CMD ["/opt/spark/bin/spark-submit", \
     "--conf", "spark.jars.ivy=/tmp/.ivy2", \
     "--packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.8", \
     "/app/streaming_job.py"]
