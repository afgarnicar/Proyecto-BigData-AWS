"""
Punto 2 - funciones para consultar la API de datos.gov.co (dataset 6jmc-vaxk): contar
filas, descargarlas página por página y definir los filtros de las tres fuentes.
La usan descargar_snapshot.py (punto 2) e ingesta_s3.py (punto 3).

Uso desde la terminal:
    python3 socrata_api.py conteos      # conteos en vivo por fuente
    python3 socrata_api.py url-resto    # URL corta (5 filas) del resto, para el navegador
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DOMAIN = "www.datos.gov.co"
DATASET_ID = "6jmc-vaxk"
RESOURCE_JSON_URL = f"https://{DOMAIN}/resource/{DATASET_ID}.json"
RESOURCE_CSV_URL = f"https://{DOMAIN}/resource/{DATASET_ID}.csv"
METADATA_URL = f"https://{DOMAIN}/api/views/{DATASET_ID}.json"

# Las nueve columnas observadas en el dataset (minúsculas, nombres de campo de Socrata).
EXPECTED_COLUMNS = [
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
ROW_ID_COLUMN = "socrata_row_id"  # nombre con el que se guarda el ":id" de Socrata

# Reparto entre fuentes por nombre exacto del departamento (no por texto parecido).
DEPARTMENT_RDS = "ANTIOQUIA"
DEPARTMENT_EC2 = "BOGOTA D.C."
WHERE_RDS = f"departamento_accidente = '{DEPARTMENT_RDS}'"
WHERE_EC2 = f"departamento_accidente = '{DEPARTMENT_EC2}'"
# El resto incluye también las filas sin departamento (NULL): con NOT IN solo,
# esas filas no quedarían en ninguna fuente y las tres no sumarían el total.
REMAINDER_WHERE = (
    f"departamento_accidente NOT IN ('{DEPARTMENT_RDS}', '{DEPARTMENT_EC2}') "
    "OR departamento_accidente IS NULL"
)

DEFAULT_PAGE_SIZE = 50000
MAX_RETRIES = 5
TIMEOUT_SECONDS = 120


def _http_get_json(url, params=None):
    """Hace un GET que devuelve JSON, con reintentos y espera exponencial."""
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    headers = {"Accept": "application/json", "User-Agent": "eafit-proyecto2-bigdata"}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            # Un 4xx (salvo 429) significa que la consulta está mal: no se reintenta.
            retryable = error.code == 429 or error.code >= 500
            if not retryable or attempt == MAX_RETRIES:
                body = error.read().decode("utf-8", errors="replace")[:500]
                raise RuntimeError(f"Error HTTP {error.code} en {url}\n{body}") from error
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            if attempt == MAX_RETRIES:
                raise RuntimeError(f"Error de red en {url}: {error}") from error
        wait_seconds = 2 ** attempt
        print(f"  reintento {attempt}/{MAX_RETRIES - 1} en {wait_seconds} s ...", file=sys.stderr)
        time.sleep(wait_seconds)


def get_metadata():
    """Devuelve los metadatos necesarios para detectar actualizaciones y cambios de esquema."""
    metadata = _http_get_json(METADATA_URL)
    return {
        "name": metadata.get("name"),
        "rows_updated_at": metadata.get("rowsUpdatedAt"),  # segundos unix
        "columns": [column["fieldName"] for column in metadata.get("columns", [])],
        "column_types": {
            column["fieldName"]: column.get("dataTypeName")
            for column in metadata.get("columns", [])
        },
    }


def count_rows(where=None):
    """Cuenta filas en el servidor, opcionalmente filtradas con una cláusula where de SoQL."""
    params = {"$select": "count(*) AS total"}
    if where:
        params["$where"] = where
    result = _http_get_json(RESOURCE_JSON_URL, params)
    return int(result[0]["total"])


def iter_rows(where=None, page_size=DEFAULT_PAGE_SIZE, verbose=True):
    """
    Entrega cada fila como diccionario, página por página, en orden estable (:id).

    Socrata omite los campos nulos en el JSON, así que una clave ausente significa NULL.
    Cada diccionario tiene las nueve columnas más ROW_ID_COLUMN.
    """
    offset = 0
    while True:
        params = {
            "$select": "*, :id",
            "$order": ":id",
            "$limit": page_size,
            "$offset": offset,
        }
        if where:
            params["$where"] = where
        page = _http_get_json(RESOURCE_JSON_URL, params)
        if verbose:
            print(f"  página desde la fila {offset:>7}: {len(page)} filas", file=sys.stderr)
        for raw_row in page:
            row = dict(raw_row)
            row[ROW_ID_COLUMN] = row.pop(":id")
            yield row
        if len(page) < page_size:
            return
        offset += page_size


def build_remainder_url(output_format="csv", page_size=DEFAULT_PAGE_SIZE, offset=0):
    """URL real, lista para copiar y pegar, de la fuente "resto de Colombia" (una página)."""
    base_url = RESOURCE_CSV_URL if output_format == "csv" else RESOURCE_JSON_URL
    params = {
        "$select": "*, :id",
        "$where": REMAINDER_WHERE,
        "$order": ":id",
        "$limit": page_size,
        "$offset": offset,
    }
    return base_url + "?" + urllib.parse.urlencode(params)


def fetch_remainder_rows(page_size=DEFAULT_PAGE_SIZE, verbose=True):
    """Fuente URL en vivo que usará la ingesta: resto de Colombia, todas las páginas."""
    return iter_rows(where=REMAINDER_WHERE, page_size=page_size, verbose=verbose)


def live_source_counts():
    """Conteos en el servidor del total y de cada una de las tres fuentes."""
    return {
        "total": count_rows(),
        "rds_antioquia": count_rows(WHERE_RDS),
        "ec2_bogota": count_rows(WHERE_EC2),
        "url_resto": count_rows(REMAINDER_WHERE),
    }


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "conteos"
    if command == "conteos":
        counts = live_source_counts()
        print(json.dumps(counts, indent=2))
        parts_sum = counts["rds_antioquia"] + counts["ec2_bogota"] + counts["url_resto"]
        print("¿las 3 fuentes suman el total?:", "SÍ" if parts_sum == counts["total"] else "NO")
    elif command == "url-resto":
        # Versión corta para abrir en el navegador y tomar la captura: 5 filas en JSON.
        # La ingesta usa fetch_remainder_rows(), que pide las páginas completas.
        print(build_remainder_url(output_format="json", page_size=5))
    else:
        print(__doc__)
        sys.exit(2)
