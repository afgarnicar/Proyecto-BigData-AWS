"""
Punto 7 - responde las 5 preguntas de negocio con la API de DataFrames de PySpark (sin SQL),
leyendo trusted/ y guardando un CSV por pregunta en refined/pyspark/ (lo usa el punto 8).

Uso (en EMR):
    spark-submit analisis_pyspark.py [--LAKE s3://bucket]
"""

import argparse

from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F

MIN_VEHICULOS_POR_TIPO = 500  # pregunta 4: con menos registros la proporción no es confiable


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--LAKE", default="s3://proyecto2-siniestros")
    args, _ = parser.parse_known_args()
    return args


def porcentaje_del_total(columna):
    """Porcentaje de cada fila sobre la suma de toda la columna (equivale a SUM(...) OVER ())."""
    return F.round(100.0 * F.col(columna) / F.sum(columna).over(Window.partitionBy()), 2)


def es_mortal():
    return F.when(F.col("gravedad_accidente") == "CON MUERTOS", 1).otherwise(0)


def q1a_departamentos(df):
    return (
        df.groupBy("departamento_accidente")
        .agg(F.count("*").alias("vehiculos"))
        .withColumn("porcentaje", porcentaje_del_total("vehiculos"))
        .orderBy(F.desc("vehiculos"))
    )


def q1b_municipios(df):
    return (
        df.groupBy("departamento_accidente", "municipio_accidente")
        .agg(F.count("*").alias("vehiculos"))
        .orderBy(F.desc("vehiculos"))
        .limit(15)
    )


def q2_tipos_vehiculo(df):
    return (
        df.groupBy("tipo_vehiculo")
        .agg(F.count("*").alias("vehiculos"))
        .withColumn("porcentaje", porcentaje_del_total("vehiculos"))
        .orderBy(F.desc("vehiculos"))
    )


def q3_evolucion_mensual(df):
    return df.groupBy("anio", "mes").agg(F.count("*").alias("vehiculos")).orderBy("anio", "mes")


def q4_proporcion_mortal(df):
    return (
        df.groupBy("tipo_vehiculo")
        .agg(F.count("*").alias("vehiculos"), F.sum(es_mortal()).alias("con_muertos"))
        .filter(F.col("vehiculos") >= MIN_VEHICULOS_POR_TIPO)
        .withColumn("porcentaje_con_muertos", F.round(100.0 * F.col("con_muertos") / F.col("vehiculos"), 2))
        .orderBy(F.desc("porcentaje_con_muertos"))
    )


def q5_antiguedad_gravedad(df):
    edad = F.col("edad_vehiculo")
    rango = (
        F.when(edad <= 5, "01) 0-5 anios")
        .when(edad <= 10, "02) 6-10 anios")
        .when(edad <= 15, "03) 11-15 anios")
        .when(edad <= 20, "04) 16-20 anios")
        .when(edad <= 30, "05) 21-30 anios")
        .otherwise("06) mas de 30 anios")
    )
    return (
        df.filter(edad.isNotNull() & ~F.col("edad_fuera_rango"))  # excluye NULL y edades > 100
        .withColumn("rango_edad", rango)
        .groupBy("rango_edad")
        .agg(F.count("*").alias("vehiculos"), F.sum(es_mortal()).alias("con_muertos"))
        .withColumn("porcentaje_con_muertos", F.round(100.0 * F.col("con_muertos") / F.col("vehiculos"), 2))
        .orderBy("rango_edad")
    )


PREGUNTAS = [
    ("q1a_departamentos", q1a_departamentos),
    ("q1b_municipios", q1b_municipios),
    ("q2_tipos_vehiculo", q2_tipos_vehiculo),
    ("q3_evolucion_mensual", q3_evolucion_mensual),
    ("q4_proporcion_mortal", q4_proporcion_mortal),
    ("q5_antiguedad_gravedad", q5_antiguedad_gravedad),
]


def main():
    args = parse_args()
    lake = args.LAKE.rstrip("/")
    spark = SparkSession.builder.appName("analisis_pyspark").getOrCreate()

    vehiculos = spark.read.parquet(f"{lake}/trusted/vehiculos").cache()
    print(f"Vehículos involucrados en trusted: {vehiculos.count()}")

    for nombre, calcular in PREGUNTAS:
        resultado = calcular(vehiculos)
        print(f"\n=== {nombre} ===")
        resultado.show(60, truncate=False)
        # coalesce(1): un solo archivo CSV por pregunta (son pocas filas).
        destino = f"{lake}/refined/pyspark/{nombre}"
        resultado.coalesce(1).write.mode("overwrite").option("header", True).csv(destino)
        print(f"Guardado en: {destino}")


if __name__ == "__main__":
    main()
