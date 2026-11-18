"""
Punto 8 - función Lambda que, llamada por API Gateway, devuelve en JSON los resultados
de las 5 preguntas que el punto 7 guardó en refined/pyspark/ del bucket de S3.

Rutas:  GET /preguntas  y  GET /resultados/{pregunta}
Variable de entorno: BUCKET (por defecto proyecto2-siniestros). Rol: LabRole.
"""

import csv
import io
import json
import os

import boto3

BUCKET = os.environ.get("BUCKET", "proyecto2-siniestros")
PREFIX = "refined/pyspark"

# Lista cerrada: la API solo acepta estos nombres (evita leer rutas arbitrarias de S3).
PREGUNTAS = {
    "q1a_departamentos": "1. Vehículos involucrados por departamento",
    "q1b_municipios": "1. Top 15 municipios con más vehículos involucrados",
    "q2_tipos_vehiculo": "2. Tipos de vehículo más frecuentemente involucrados",
    "q3_evolucion_mensual": "3. Evolución mensual de vehículos involucrados",
    "q4_proporcion_mortal": "4. Proporción de registros CON MUERTOS por tipo (tipos con al menos 500 registros)",
    "q5_antiguedad_gravedad": "5. Proporción de registros CON MUERTOS por antigüedad del vehículo",
}

_s3 = None  # cliente de S3; se crea en la primera llamada y se reutiliza


def s3_client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def respuesta(status, cuerpo):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(cuerpo, ensure_ascii=False),
    }


def convertir(valor):
    """Los CSV traen todo como texto: '175618' -> 175618, '39.0' -> 39.0."""
    for tipo in (int, float):
        try:
            return tipo(valor)
        except ValueError:
            pass
    return valor


def leer_resultado(pregunta):
    """Busca el CSV que Spark escribió en refined/pyspark/<pregunta>/ y lo convierte en filas."""
    listado = s3_client().list_objects_v2(Bucket=BUCKET, Prefix=f"{PREFIX}/{pregunta}/")
    claves = [obj["Key"] for obj in listado.get("Contents", []) if obj["Key"].endswith(".csv")]
    if not claves:
        return None
    contenido = s3_client().get_object(Bucket=BUCKET, Key=claves[0])["Body"].read().decode("utf-8")
    lector = csv.DictReader(io.StringIO(contenido))
    filas = [{columna: convertir(valor) for columna, valor in fila.items()} for fila in lector]
    return {"columnas": lector.fieldnames, "filas": filas}


def lambda_handler(event, context):
    ruta = event.get("rawPath", "")
    parametros = event.get("pathParameters") or {}

    if ruta.rstrip("/").endswith("/preguntas"):
        return respuesta(200, {"preguntas": [{"id": k, "descripcion": v} for k, v in PREGUNTAS.items()]})

    pregunta = parametros.get("pregunta")
    if pregunta not in PREGUNTAS:
        return respuesta(404, {"error": f"Pregunta no encontrada: {pregunta}", "disponibles": list(PREGUNTAS)})

    resultado = leer_resultado(pregunta)
    if resultado is None:
        return respuesta(404, {"error": f"No hay resultados en s3://{BUCKET}/{PREFIX}/{pregunta}/"})

    return respuesta(200, {
        "pregunta": pregunta,
        "descripcion": PREGUNTAS[pregunta],
        "unidad": "vehículos involucrados (una fila = un vehículo, no un accidente)",
        **resultado,
    })
