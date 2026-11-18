# Proyecto 2 Big Data — Vehículos involucrados en siniestros viales en Colombia

EAFIT · SI3007 Sistemas Distribuidos / ST0263 Tópicos Especiales en Telemática · 2026-2

- **Integrantes:** Andrés Felipe Garnica Roa y Alberto Cervantes Forero
- **Nube:** AWS (AWS Academy Learner Lab, región `us-east-1`)

## Qué hace este proyecto

Construye un pipeline de Big Data en AWS sobre el dataset público
[Vehículos involucrados en un accidente de tránsito (6jmc-vaxk)](https://www.datos.gov.co/Transporte/VEHICULOS-INVOLUCRADOS-EN-UN-ACCIDENTE-DE-TRANSITO/6jmc-vaxk)
de Datos Abiertos Colombia / RUNT, para responder cinco preguntas de negocio sobre 450.335 registros (2022–2026).

**Unidad de observación:** cada fila es **un vehículo involucrado**, no un accidente único.

Cada uno de los 8 puntos del enunciado tiene su carpeta (`01_caso_estudio/` … `08_visualizacion/`) con un README que explica el código, las decisiones, el paso a paso en AWS y las evidencias (`evidencias/`).

## Principales resultados

Corresponden al corte consultado entre el 14 y el 16 de noviembre de 2026; el origen público se puede actualizar.

| Pregunta | Resultado |
|---|---|
| 1. Departamentos y municipios | Antioquia (39,0 %), Bogotá D.C. (14,0 %) y Valle del Cauca (12,6 %). Municipios: Medellín (111.235), Bogotá (62.990), Cali (34.531) |
| 2. Tipos de vehículo | Motocicleta (56,7 %), automóvil (22,2 %), camioneta (8,5 %) |
| 3. Evolución mensual | Entre 8.075 y 11.446 por mes de 01/2022 a 06/2024; pico atípico en 07/2024 (28.854); descenso desde fines de 2024; entre 5.248 y 6.006 por mes en 2025; 08 y 09/2026 incompletos |
| 4. Proporción de registros `CON MUERTOS` por tipo (≥ 500 registros) | Tractocamión 28,8 %, volqueta 19,6 %, camión 18,1 %; motocicleta 5,1 %; automóvil 2,5 % |
| 5. Antigüedad y gravedad | Alrededor de 5 % hasta 20 años; 7,1 % entre 21 y 30 años; 10,4 % con más de 30 años (relación descriptiva, no causal) |

## Cómo reproducir el proyecto desde cero

### Requisitos

- Una cuenta de AWS (por ejemplo AWS Academy Learner Lab), región **us-east-1**.
- Python 3.9 o superior, `ssh` y `scp` (incluidos en macOS, Linux y Windows 10+).
- Las librerías de `requirements.txt` (cada una indica en qué punto se usa). No se necesita Docker: el procesamiento corre en servicios de AWS que ya traen su entorno (Glue, EMR, Lambda).

### Orden

Cada paso usa lo que deja el anterior. El detalle está en el README de cada carpeta.

| Paso | Qué se crea | Dónde |
|---|---|---|
| 1 | Snapshot local: CSV de Antioquia y Bogotá + manifiesto (`descargar_snapshot.py`). Los CSV no están en el repositorio: se generan con este script | tu computador |
| 2 | EC2 (`t3.micro`, `LabInstanceProfile`) con el CSV de Bogotá; RDS MariaDB con la tabla de Antioquia | [`02_fuentes/`](02_fuentes/README.md) |
| 3 | Bucket S3; `ingesta_s3.py` + `.env` en la EC2; cron cada hora | [`03_ingesta_s3/`](03_ingesta_s3/README.md) |
| 4 | Job de Glue `raw_a_trusted` (LabRole, G.1X, 2 workers) | [`04_glue_spark/`](04_glue_spark/README.md) |
| 5 | Base `siniestros` + crawler en Glue; clúster EMR con Hive y Spark usando el Glue Data Catalog | [`05_catalogacion/`](05_catalogacion/README.md) |
| 6 | Las 6 consultas en Athena; `ejecutar_consultas_emr.sh` en EMR | [`06_sql_analitico/`](06_sql_analitico/README.md) |
| 7 | `spark-submit analisis_pyspark.py` en EMR (después, terminar el clúster) | [`07_pyspark/`](07_pyspark/README.md) |
| 8 | Lambda + HTTP API; Streamlit en la EC2; `graficos.py` en tu computador | [`08_visualizacion/`](08_visualizacion/README.md) |

### Si usas otro nombre de bucket

Los nombres de bucket son únicos en todo AWS: quien reproduzca el proyecto debe crear el suyo. El nombre `proyecto2-siniestros` aparece en:

| Archivo | Qué cambiar |
|---|---|
| `03_ingesta_s3/ingesta.env.example` (→ `.env` en la EC2) | `S3_BUCKET=` |
| `04_glue_spark/scripts/raw_a_trusted.py` | Sin editar: parámetro del job `--LAKE s3://<bucket>`. Además, Script path y Temporary path del job |
| `06_sql_analitico/ejecutar_consultas_emr.sh` | `BUCKET="s3://<bucket>"` |
| `07_pyspark/scripts/analisis_pyspark.py` | Sin editar: `spark-submit analisis_pyspark.py --LAKE s3://<bucket>` |
| `08_visualizacion/lambda/api_resultados.py` | Sin editar: variable de entorno `BUCKET` de la Lambda |
| Crawler de Glue y ubicación de resultados de Athena | Rutas `s3://<bucket>/...` en la consola |

Los comandos de los README usan `proyecto2-siniestros`; reemplazarlo en ellos también.
