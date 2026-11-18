"""
Punto 2 - descarga el dataset 6jmc-vaxk de la API Socrata y guarda en CSV las filas
de Antioquia (fuente RDS) y de Bogotá D.C. (fuente EC2), junto con un manifest.json
que registra conteos, comprobaciones y la huella SHA-256 de cada archivo.

Uso:
    python3 02_fuentes/scripts/descargar_snapshot.py
"""

import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

import socrata_api as api

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
POINT_DIR = os.path.dirname(SCRIPT_DIR)  # 02_fuentes/
DEFAULT_OUTPUT_DIR = os.path.join(POINT_DIR, "data")
EVIDENCE_DIR = os.path.join(POINT_DIR, "evidencias")

CSV_COLUMNS = [api.ROW_ID_COLUMN] + api.EXPECTED_COLUMNS  # orden de columnas de los CSV

# Nombre interno de cada comprobación (se guarda así en manifest.json) -> mensaje en pantalla.
CHECK_DESCRIPTIONS = {
    "columns_match_expected": "las 9 columnas son las esperadas",
    "no_unexpected_fields": "no llegaron campos inesperados",
    "dataset_not_updated_during_download": "el dataset no cambió durante la descarga",
    "downloaded_equals_server_total": "filas descargadas = total del servidor",
    "row_ids_unique_no_page_overlap": "no hay filas repetidas entre páginas",
    "sources_sum_equals_total": "los 3 filtros SoQL suman el total del servidor",
    "rds_count_matches_server": "conteo de Antioquia (RDS) = servidor",
    "ec2_count_matches_server": "conteo de Bogotá (EC2) = servidor",
    "url_count_matches_server": "conteo del resto (URL) = servidor",
}

# Solo se guardan en disco las dos fuentes que se suben a AWS.
OUTPUT_FILES = {
    "rds_antioquia": "fuente_rds_antioquia.csv",
    "ec2_bogota": "fuente_ec2_bogota.csv",
}
SOURCES = ["rds_antioquia", "ec2_bogota", "url_resto"]


def source_of(row):
    """Reparto por categoría exacta. Debe coincidir con los filtros SoQL de socrata_api.py."""
    department = row.get("departamento_accidente")
    if department == api.DEPARTMENT_RDS:
        return "rds_antioquia"
    if department == api.DEPARTMENT_EC2:
        return "ec2_bogota"
    return "url_resto"  # incluye departamentos NULL, igual que REMAINDER_WHERE


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def open_csv_writer(path):
    # Fin de línea "\n" + UTF-8: lo que espera el script LOAD DATA de MariaDB.
    file = open(path, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    return file, writer


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    started_at = datetime.now(timezone.utc)
    snapshot_id = "snapshot_" + started_at.strftime("%Y%m%dT%H%M%SZ")
    snapshot_dir = os.path.join(args.output_dir, snapshot_id)
    os.makedirs(snapshot_dir, exist_ok=False)
    print(f"Carpeta del snapshot: {snapshot_dir}")

    # 1) Metadatos + revisión del esquema ANTES de descargar algo pesado.
    metadata_before = api.get_metadata()
    if metadata_before["columns"] != api.EXPECTED_COLUMNS:
        sys.exit(
            "ABORTADO: las columnas del dataset cambiaron.\n"
            f"  esperadas:  {api.EXPECTED_COLUMNS}\n  encontradas: {metadata_before['columns']}"
        )
    counts_before = api.live_source_counts()
    print("Conteos del servidor antes de la descarga: ", counts_before)

    # 2) Recorre todas las filas: las de RDS y EC2 se escriben directo en su CSV
    #    (poco uso de memoria); las del resto solo se cuentan.
    files, writers = {}, {}
    for key, file_name in OUTPUT_FILES.items():
        files[key], writers[key] = open_csv_writer(os.path.join(snapshot_dir, file_name))

    local_counts = {source: 0 for source in SOURCES}
    null_counts = {column: 0 for column in api.EXPECTED_COLUMNS}
    seen_row_ids = set()
    unexpected_fields = set()

    try:
        for row in api.iter_rows():
            unexpected_fields.update(set(row) - set(CSV_COLUMNS))
            for column in api.EXPECTED_COLUMNS:
                if row.get(column) is None:  # clave ausente en el JSON de Socrata == NULL
                    null_counts[column] += 1
            seen_row_ids.add(row[api.ROW_ID_COLUMN])

            source = source_of(row)
            local_counts[source] += 1
            if source in writers:
                writers[source].writerow({column: row.get(column, "") for column in CSV_COLUMNS})
    finally:
        for file in files.values():
            file.close()

    # 3) Vuelve a leer el estado del servidor para detectar cambios durante la descarga.
    metadata_after = api.get_metadata()
    counts_after = api.live_source_counts()
    print("Conteos del servidor después de la descarga:", counts_after)

    total_downloaded = sum(local_counts.values())
    checks = {
        "columns_match_expected": metadata_before["columns"] == api.EXPECTED_COLUMNS,
        "no_unexpected_fields": not unexpected_fields,
        "dataset_not_updated_during_download": (
            metadata_before["rows_updated_at"] == metadata_after["rows_updated_at"]
            and counts_before == counts_after
        ),
        "downloaded_equals_server_total": total_downloaded == counts_before["total"],
        "row_ids_unique_no_page_overlap": len(seen_row_ids) == total_downloaded,
        # Los 3 filtros SoQL, contados en el servidor, deben cubrir todo el dataset.
        "sources_sum_equals_total": (
            counts_before["rds_antioquia"] + counts_before["ec2_bogota"] + counts_before["url_resto"]
            == counts_before["total"]
        ),
        "rds_count_matches_server": local_counts["rds_antioquia"] == counts_before["rds_antioquia"],
        "ec2_count_matches_server": local_counts["ec2_bogota"] == counts_before["ec2_bogota"],
        "url_count_matches_server": local_counts["url_resto"] == counts_before["url_resto"],
    }

    file_info = {}
    for key, file_name in OUTPUT_FILES.items():
        path = os.path.join(snapshot_dir, file_name)
        file_info[key] = {
            "file": file_name,
            "data_rows": local_counts[key],  # sin contar la línea de encabezado
            "bytes": os.path.getsize(path),
            "sha256": sha256_of(path),
        }

    manifest = {
        "snapshot_id": snapshot_id,
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "id": api.DATASET_ID,
            "name": metadata_before["name"],
            "resource_url": api.RESOURCE_JSON_URL,
            "rows_updated_at_unix": metadata_before["rows_updated_at"],
            "rows_updated_at_utc": (
                datetime.fromtimestamp(metadata_before["rows_updated_at"], timezone.utc).isoformat()
                if metadata_before["rows_updated_at"] else None
            ),
            "column_types": metadata_before["column_types"],
        },
        "unit_of_observation": "una fila = un vehículo involucrado en un siniestro vial (NO un accidente)",
        "pagination": {"order_by": ":id", "page_size": api.DEFAULT_PAGE_SIZE},
        "source_filters_soql": {
            "rds_antioquia": api.WHERE_RDS,
            "ec2_bogota": api.WHERE_EC2,
            "url_resto": api.REMAINDER_WHERE,
        },
        "server_counts_before": counts_before,
        "server_counts_after": counts_after,
        "local_counts": local_counts,
        "null_counts": null_counts,
        "unexpected_fields": sorted(unexpected_fields),
        "files": file_info,
        "checks": checks,
        "all_checks_passed": all(checks.values()),
    }

    manifest_path = os.path.join(snapshot_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as file:
        json.dump(manifest, file, indent=2, ensure_ascii=False)
    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    evidence_path = os.path.join(EVIDENCE_DIR, f"manifest_{snapshot_id}.json")
    with open(evidence_path, "w", encoding="utf-8") as file:
        json.dump(manifest, file, indent=2, ensure_ascii=False)

    print("\nConteos locales:", local_counts)
    print("Valores NULL por columna:", {k: v for k, v in null_counts.items() if v})
    print("Comprobaciones:")
    for name, passed in checks.items():
        print(f"  [{'OK' if passed else 'FALLA'}] {CHECK_DESCRIPTIONS[name]}")
    print(f"\nManifiesto: {manifest_path}\nCopia en evidencias: {evidence_path}")

    if not manifest["all_checks_passed"]:
        sys.exit("Algunas comprobaciones FALLARON. Revisa el manifiesto; si el dataset se actualizó, vuelve a ejecutar.")
    print("Todas las comprobaciones pasaron.")


if __name__ == "__main__":
    main()
