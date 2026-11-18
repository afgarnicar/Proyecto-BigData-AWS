#!/bin/bash
# Punto 6 - ejecuta las 6 consultas en Hive y en Spark SQL (nodo principal de EMR)
# y guarda los resultados en ~/resultados/ y en S3 (refined/sql/).
# Uso, en la carpeta que contiene consultas/:  bash ejecutar_consultas_emr.sh

BUCKET="s3://proyecto2-siniestros"
mkdir -p ~/resultados/hive ~/resultados/sparksql

for archivo in consultas/*.sql; do
  nombre=$(basename "$archivo" .sql)

  echo "=== Hive: $nombre ==="
  hive --hiveconf hive.cli.print.header=true -f "$archivo" 2>/dev/null \
    | tee ~/resultados/hive/"$nombre".txt

  echo "=== Spark SQL: $nombre ==="
  spark-sql --hiveconf hive.cli.print.header=true -f "$archivo" 2>/dev/null \
    | tee ~/resultados/sparksql/"$nombre".txt
done

aws s3 cp ~/resultados/ "$BUCKET/refined/sql/" --recursive
echo "Resultados guardados en ~/resultados/ y en $BUCKET/refined/sql/"
