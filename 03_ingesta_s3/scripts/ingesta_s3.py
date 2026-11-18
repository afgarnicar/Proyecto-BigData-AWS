"""
Punto 3 - lee las tres fuentes (RDS, el CSV de la EC2 y la API) y deja una copia de cada
una en la zona raw/ del bucket de S3, más un log de la ejecución en logs/.
Se ejecuta en la EC2, a mano o con cron. La configuración se lee del .env junto al script.

Uso:
    python3 ingesta_s3.py
"""

import argparse
import csv
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# socrata_api.py está junto a este script en la EC2, o en 02_fuentes/scripts en el repositorio.
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(1, os.path.join(SCRIPT_DIR, "..", "..", "02_fuentes", "scripts"))
import socrata_api as api

CSV_COLUMNS = [api.ROW_ID_COLUMN] + api.EXPECTED_COLUMNS
COLOMBIA = ZoneInfo("America/Bogota")


def load_config(path):
    """Lee un archivo .env simple (CLAVE=valor por línea) sin librerías externas."""
    config = {}
    with open(path, encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                config[key.strip()] = value.strip()
    required = ["S3_BUCKET", "RDS_HOST", "RDS_USER", "RDS_PASSWORD", "RDS_SSL_CA", "EC2_CSV_PATH"]
    missing = [key for key in required if not config.get(key)]
    if missing:
        sys.exit(f"Faltan valores en {path}: {', '.join(missing)}")
    return config


def write_csv(path, rows):
    """Escribe filas (diccionarios) con el mismo formato de CSV del punto 2. Devuelve el conteo."""
    count = 0
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column) for column in CSV_COLUMNS})
            count += 1
    return count


def extract_rds(config, output_path):
    """Lee la tabla de Antioquia en RDS con conexión cifrada y verificada."""
    import pymysql  # se importa aquí para poder probar las otras fuentes sin instalarlo

    connection = pymysql.connect(
        host=config["RDS_HOST"],
        port=int(config.get("RDS_PORT", "3306")),
        user=config["RDS_USER"],
        password=config["RDS_PASSWORD"],
        database=config.get("RDS_DATABASE", "siniestros_viales"),
        ssl_ca=config["RDS_SSL_CA"],
        ssl_verify_cert=True,
        ssl_verify_identity=True,
        cursorclass=pymysql.cursors.SSDictCursor,  # lee fila por fila, sin cargar todo en memoria
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT {', '.join(CSV_COLUMNS)} FROM vehiculos_involucrados ORDER BY socrata_row_id")
            rows_written = write_csv(output_path, cursor)
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total FROM vehiculos_involucrados")
            expected = cursor.fetchone()["total"]
    finally:
        connection.close()
    return rows_written, expected


def extract_ec2(config, output_path):
    """Toma el CSV local de Bogotá tal cual, después de revisar su encabezado."""
    source_path = config["EC2_CSV_PATH"]
    with open(source_path, newline="", encoding="utf-8") as file:
        reader = csv.reader(file)
        header = next(reader)
        if header != CSV_COLUMNS:
            raise ValueError(f"Encabezado inesperado en {source_path}: {header}")
        rows = sum(1 for _ in reader)
    shutil.copyfile(source_path, output_path)
    return rows, rows  # el archivo es la fuente misma: lo esperado es lo que tiene


def extract_url(config, output_path):
    """
    Lee en vivo la API con el filtro del resto de Colombia y guarda cada registro
    tal como llega, uno por línea (JSON Lines). Los campos NULL no aparecen, igual que en la API.
    """
    expected = api.count_rows(api.REMAINDER_WHERE)
    rows_written = 0
    with open(output_path, "w", encoding="utf-8") as file:
        for row in api.fetch_remainder_rows(verbose=False):
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
            rows_written += 1
    return rows_written, expected


SOURCES = [
    # (nombre, función, carpeta en raw/, nombre del archivo)
    ("rds", extract_rds, "rds", "vehiculos_antioquia.csv"),
    ("ec2", extract_ec2, "ec2", "vehiculos_bogota.csv"),
    ("url", extract_url, "url", "vehiculos_resto.json"),
]


class Destination:
    """Guarda en S3, o en una carpeta local cuando se usa --local-dir para probar."""

    def __init__(self, config, local_dir):
        self.bucket = config["S3_BUCKET"]
        self.local_dir = local_dir
        if not local_dir:
            import boto3  # usa los permisos de LabInstanceProfile: no hay claves en el código
            self.s3 = boto3.client("s3", region_name=config.get("AWS_REGION", "us-east-1"))

    def put_file(self, local_path, key):
        if self.local_dir:
            target = os.path.join(self.local_dir, key)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(local_path, target)
            return target
        self.s3.upload_file(local_path, self.bucket, key)
        return f"s3://{self.bucket}/{key}"

    def put_text(self, text, key):
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".json") as file:
            file.write(text)
        try:
            return self.put_file(file.name, key)
        finally:
            os.remove(file.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--local-dir", help="guardar en esta carpeta en vez de subir a S3 (para probar)")
    parser.add_argument("--env", default=os.path.join(SCRIPT_DIR, ".env"), help="archivo de configuración")
    args = parser.parse_args()

    config = load_config(args.env)
    destination = Destination(config, args.local_dir)

    started_utc = datetime.now(timezone.utc)
    started_local = started_utc.astimezone(COLOMBIA)
    ingestion_date = started_local.strftime("%Y-%m-%d")
    print(f"Ingesta iniciada: {started_local:%Y-%m-%d %H:%M:%S} (hora de Colombia)")

    results = {}
    with tempfile.TemporaryDirectory() as work_dir:
        for name, extract, folder, file_name in SOURCES:
            key = f"raw/{folder}/fecha_ingesta={ingestion_date}/{file_name}"
            local_path = os.path.join(work_dir, file_name)
            begin = time.time()
            try:
                rows, expected = extract(config, local_path)
                location = destination.put_file(local_path, key)
                results[name] = {
                    "status": "ok" if rows == expected else "diferencia",
                    "rows": rows,
                    "expected_rows": expected,
                    "destination": location,
                }
            except Exception as error:  # una fuente que falla no detiene a las demás
                results[name] = {"status": "error", "error": f"{type(error).__name__}: {error}"}
            results[name]["seconds"] = round(time.time() - begin, 1)
            print(f"  [{results[name]['status'].upper()}] {name}: {results[name]}")

    finished_local = datetime.now(timezone.utc).astimezone(COLOMBIA)
    log = {
        "started_colombia": started_local.isoformat(),
        "started_utc": started_utc.isoformat(),
        "finished_colombia": finished_local.isoformat(),
        "ingestion_date": ingestion_date,
        "bucket": config["S3_BUCKET"],
        "sources": results,
        "all_ok": all(result["status"] == "ok" for result in results.values()),
    }
    log_key = f"logs/ingesta_{started_local:%Y-%m-%d_%H-%M-%S}.json"
    log_location = destination.put_text(json.dumps(log, indent=2, ensure_ascii=False), log_key)
    print(f"Log: {log_location}")

    if not log["all_ok"]:
        print("La ingesta terminó con problemas: revisar el log.")
        sys.exit(1)
    print("Ingesta completa: las 3 fuentes quedaron en raw/.")


if __name__ == "__main__":
    main()
