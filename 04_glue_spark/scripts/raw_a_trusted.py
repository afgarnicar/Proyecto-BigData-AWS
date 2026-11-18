"""
Punto 4 - job de AWS Glue (Spark) que lee las tres fuentes de un día de raw/ (dos CSV y un
JSON), las une y estandariza en una sola tabla, y la escribe en trusted/ como Parquet
particionado por año, junto con un reporte de calidad en logs/.

Parámetros opcionales:
    --FECHA_INGESTA AAAA-MM-DD   día a procesar (por defecto, el más reciente con las tres fuentes)
    --LAKE s3://bucket           raíz del data lake (por defecto s3://proyecto2-siniestros)
"""

import argparse
import json
import os
import re
from datetime import datetime, timezone

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, StructField, StructType

TEXT_COLUMNS = [
    "socrata_row_id",
    "marca_vehiculo",
    "modelo_vehiculo",
    "tipo_vehiculo",
    "edad_vehiculo",
    "fecha_accidente",
    "gravedad_accidente",
    "departamento_accidente",
    "municipio_accidente",
    "autoridad_de_transito",
]
SOURCES = {
    # fuente: (carpeta en raw/, archivo, formato)
    "rds": ("rds", "vehiculos_antioquia.csv", "csv"),
    "ec2": ("ec2", "vehiculos_bogota.csv", "csv"),
    "url": ("url", "vehiculos_resto.json", "json"),
}
DATE_FOLDER = re.compile(r"fecha_ingesta=(\d{4}-\d{2}-\d{2})")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--FECHA_INGESTA", default="")
    parser.add_argument("--LAKE", default="s3://proyecto2-siniestros")
    # Glue agrega sus propios parámetros (--JOB_NAME, etc.): se ignoran.
    args, _ = parser.parse_known_args()
    return args


def list_ingestion_dates(lake, folder):
    """Fechas de ingesta disponibles en raw/<folder>/, en S3 o en una carpeta local."""
    if lake.startswith("s3://"):
        import boto3

        bucket = lake[len("s3://"):].strip("/")
        response = boto3.client("s3").list_objects_v2(
            Bucket=bucket, Prefix=f"raw/{folder}/", Delimiter="/"
        )
        names = [item["Prefix"] for item in response.get("CommonPrefixes", [])]
    else:
        path = os.path.join(lake, "raw", folder)
        names = os.listdir(path) if os.path.isdir(path) else []
    return {match.group(1) for name in names if (match := DATE_FOLDER.search(name))}


def choose_ingestion_date(lake, requested):
    """Usa la fecha pedida, o la más reciente que exista en las tres fuentes."""
    dates_by_source = {name: list_ingestion_dates(lake, folder) for name, (folder, _, _) in SOURCES.items()}
    common_dates = set.intersection(*dates_by_source.values())
    if requested:
        missing = [name for name, dates in dates_by_source.items() if requested not in dates]
        if missing:
            raise SystemExit(f"La fecha {requested} no existe en raw/ para: {', '.join(missing)}")
        return requested
    if not common_dates:
        raise SystemExit(f"No hay una fecha de ingesta común a las tres fuentes: {dates_by_source}")
    return max(common_dates)


def read_source(spark, lake, name, ingestion_date):
    """Lee una fuente de raw como texto, sin interpretar tipos, y le agrega su origen."""
    folder, file_name, file_format = SOURCES[name]
    path = f"{lake}/raw/{folder}/fecha_ingesta={ingestion_date}/{file_name}"
    if file_format == "csv":
        df = spark.read.option("header", True).option("inferSchema", False).csv(path)
    else:
        # En el JSON de Socrata un campo NULL no aparece: con un esquema fijo queda como NULL.
        schema = StructType([StructField(column, StringType()) for column in TEXT_COLUMNS])
        df = spark.read.schema(schema).json(path)
    return df.select(*TEXT_COLUMNS).withColumn("fuente", F.lit(name))


def standardize(df, ingestion_date):
    """
    Textos sin espacios sobrantes (vacío -> NULL); edad y modelo a enteros; fecha 'MM/YYYY'
    -> anio y mes; marca edad_fuera_rango (< 0 o > 100) sin borrar filas.
    """
    for column in TEXT_COLUMNS:
        trimmed = F.trim(F.col(column))
        df = df.withColumn(column, F.when(trimmed == "", None).otherwise(trimmed))

    date_pattern = r"^(\d{2})/(\d{4})$"
    valid_date = F.col("fecha_accidente").rlike(date_pattern)
    month = F.regexp_extract("fecha_accidente", date_pattern, 1).cast("int")
    year = F.regexp_extract("fecha_accidente", date_pattern, 2).cast("int")

    return (
        df.withColumn("modelo_texto", F.col("modelo_vehiculo"))
        .withColumn("edad_texto", F.col("edad_vehiculo"))
        .withColumn("modelo_vehiculo", F.col("modelo_vehiculo").cast("int"))
        .withColumn("edad_vehiculo", F.col("edad_vehiculo").cast("int"))
        .withColumn("mes", F.when(valid_date, month))
        .withColumn("anio", F.when(valid_date, year))
        .withColumn(
            "edad_fuera_rango",
            F.col("edad_vehiculo").isNotNull() & ((F.col("edad_vehiculo") < 0) | (F.col("edad_vehiculo") > 100)),
        )
        .withColumn("fecha_ingesta", F.lit(ingestion_date))
    )


def quality_report(clean, written, ingestion_date):
    """Cuenta entradas y salidas por fuente, NULL y anomalías, para el reporte JSON."""
    def counts_by_source(df):
        return {row["fuente"]: row["count"] for row in df.groupBy("fuente").count().collect()}

    input_counts = counts_by_source(clean)
    output_counts = counts_by_source(written)
    row = clean.agg(
        F.count("*").alias("total"),
        F.sum(F.col("edad_vehiculo").isNull().cast("int")).alias("edad_null"),
        F.sum(F.col("modelo_vehiculo").isNull().cast("int")).alias("modelo_null"),
        # Texto que existía pero no se pudo convertir a número (valor inválido en origen).
        F.sum((F.col("edad_texto").isNotNull() & F.col("edad_vehiculo").isNull()).cast("int")).alias("edad_no_numerica"),
        F.sum((F.col("modelo_texto").isNotNull() & F.col("modelo_vehiculo").isNull()).cast("int")).alias("modelo_no_numerico"),
        F.sum(F.col("anio").isNull().cast("int")).alias("fecha_invalida"),
        F.sum(F.col("edad_fuera_rango").cast("int")).alias("edad_fuera_rango"),
    ).first().asDict()
    null_counts = {
        column: clean.filter(F.col(column).isNull()).count()
        for column in TEXT_COLUMNS
        if column not in ("edad_vehiculo", "modelo_vehiculo")
    }
    return {
        "fecha_ingesta": ingestion_date,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "rows_in_by_source": input_counts,
        "rows_out_by_source": output_counts,
        "rows_in_equal_rows_out": input_counts == output_counts,
        "metrics": row,
        "null_counts_text_columns": null_counts,
    }


def save_report(lake, report):
    text = json.dumps(report, indent=2, ensure_ascii=False)
    key = f"logs/trusted_{report['fecha_ingesta']}.json"
    if lake.startswith("s3://"):
        import boto3

        bucket = lake[len("s3://"):].strip("/")
        boto3.client("s3").put_object(Bucket=bucket, Key=key, Body=text.encode("utf-8"))
        return f"s3://{bucket}/{key}"
    path = os.path.join(lake, key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        file.write(text)
    return path


def main():
    args = parse_args()
    lake = args.LAKE.rstrip("/")
    ingestion_date = choose_ingestion_date(lake, args.FECHA_INGESTA)
    print(f"Procesando fecha_ingesta={ingestion_date} desde {lake}/raw/")

    spark = SparkSession.builder.appName("raw_a_trusted").getOrCreate()

    sources = [read_source(spark, lake, name, ingestion_date) for name in SOURCES]
    union = sources[0]
    for other in sources[1:]:
        union = union.unionByName(other)
    clean = standardize(union, ingestion_date).cache()

    output_columns = [
        "socrata_row_id", "fuente", "marca_vehiculo", "modelo_vehiculo", "tipo_vehiculo",
        "edad_vehiculo", "edad_fuera_rango", "fecha_accidente", "anio", "mes",
        "gravedad_accidente", "departamento_accidente", "municipio_accidente",
        "autoridad_de_transito", "fecha_ingesta",
    ]
    trusted_path = f"{lake}/trusted/vehiculos"
    # overwrite: trusted refleja siempre un único día de ingesta (no se acumulan copias).
    clean.select(*output_columns).write.mode("overwrite").partitionBy("anio").parquet(trusted_path)

    written = spark.read.parquet(trusted_path)  # se relee lo escrito para validarlo
    report = quality_report(clean, written, ingestion_date)
    location = save_report(lake, report)

    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"Trusted: {trusted_path}\nReporte: {location}")
    if not report["rows_in_equal_rows_out"]:
        raise SystemExit("Las filas de salida no coinciden con las de entrada.")


if __name__ == "__main__":
    main()
