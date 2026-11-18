# Punto 4 — Preparación de datos RAW → TRUSTED con AWS Glue y Apache Spark

## Qué hace

Un **job de AWS Glue** ejecuta un programa de **Apache Spark** (`raw_a_trusted.py`). AWS levanta las máquinas, corre el programa y las apaga. El job lee las tres fuentes de un día de ingesta, las estandariza en una sola tabla y la guarda en Parquet.

```text
raw/rds/fecha_ingesta=.../vehiculos_antioquia.csv  (CSV)  ─┐
raw/ec2/fecha_ingesta=.../vehiculos_bogota.csv     (CSV)  ─┼─> Glue Job (Spark) ─> trusted/vehiculos/anio=2022/*.parquet
raw/url/fecha_ingesta=.../vehiculos_resto.json     (JSON) ─┘                                         anio=2023/ ...
                                                                                 + logs/trusted_AAAA-MM-DD.json
```

## Reglas de preparación

| Regla | Detalle |
|---|---|
| Origen de cada fila | Columna `fuente` (`rds`, `ec2`, `url`) y `fecha_ingesta` |
| Formatos distintos → uno solo | CSV y JSON se leen como texto y se unen por nombre de columna |
| Textos | Sin espacios sobrantes; texto vacío → NULL |
| Números | `edad_vehiculo` y `modelo_vehiculo` → enteros. Los NULL siguen siendo NULL (no se imputan) |
| Fecha | `fecha_accidente` `MM/YYYY` → columnas numéricas `anio` y `mes`. Se conserva también el texto original |
| Anomalías | `edad_fuera_rango` = true si la edad es < 0 o > 100. **Se marca, no se borra** |
| Duplicados | **No se eliminan**: no hay id de accidente y dos filas iguales pueden ser dos vehículos distintos |
| Salida | Parquet particionado por `anio`, en modo `overwrite`: `trusted/` refleja siempre un único día de ingesta |

**Qué día de `raw/` procesa:** el parámetro `--FECHA_INGESTA AAAA-MM-DD`, si se indica. Si no, usa la fecha más reciente que exista en las **tres** fuentes. Leer todo `raw/` duplicaría las filas, porque cada día de ingesta es una copia completa. La fecha procesada queda en el reporte.

**Validación:** después de escribir, el job vuelve a leer el Parquet y compara las filas por fuente con las de entrada. Si no coinciden, el job falla.

## Resultado de la prueba local (Spark 4.0, datos del 2026-11-16)

| Métrica | Valor |
|---|---:|
| Filas de entrada / salida | 450.335 / 450.335 (rds 175.618, ec2 62.990, url 211.727) |
| `edad_vehiculo` NULL | 20 |
| `edad_fuera_rango` | 65 |
| Fechas inválidas, edades o modelos no numéricos | 0 |
| Particiones | `anio=2022` … `anio=2026` |
| Tamaño | 96 MB en `raw/` → **9,3 MB** en Parquet |

Controles cruzados con la exploración del punto 1: 07/2024 = 28.854 filas; `CON MUERTOS` = 23.899; 0 filas de `PUERTO BOGOTÁ` en la fuente `ec2`.

## Paso a paso en AWS

Requiere que el punto 3 ya haya dejado datos en `raw/`.

### 1. Crear el job

Consola → **AWS Glue** → **ETL jobs** → **Script editor**:
- Engine: **Spark**. Opción: **Start fresh**. **Create script**.
- Borrar el código de ejemplo y pegar el contenido de `scripts/raw_a_trusted.py`.

Pestaña **Job details**:

| Campo | Valor |
|---|---|
| Name | `raw_a_trusted` |
| IAM Role | **LabRole** |
| Type | Spark |
| Glue version | Glue 6.0 (Spark 4.1, Python 3) |
| Language | Python 3 |
| Worker type | **G.1X** |
| Requested number of workers | **2** |
| Job bookmark | Disable |
| Number of retries | 0 |
| Job timeout | 15 (minutos) |

En **Advanced properties** (escribir a mano; deben empezar con `s3://` y **terminar con `/`**):
- **Script filename:** `raw_a_trusted.py`
- **Script path:** `s3://proyecto2-siniestros/scripts/`
- **Temporary path:** `s3://proyecto2-siniestros/glue-temp/` (carpeta de trabajo de Glue, separada de las zonas del data lake)

  Sin la `/` final, Glue pega el nombre del archivo a la carpeta y falla con `S3 link ... must contain a bucket and key`. Las carpetas no tienen que existir: Glue las crea al guardar.
- **Spark UI:** desactivar (evita crear otro bucket para sus logs).
- **Job parameters:** no hace falta ninguno. Para reprocesar un día concreto: clave `--FECHA_INGESTA`, valor `2026-11-16`.

**Save**.

### 2. Ejecutar

Botón **Run**. En la pestaña **Runs**, esperar a que el estado pase a **Succeeded** (unos 2 o 3 minutos, la mayor parte es el arranque de las máquinas).

Si falla, el mensaje está en **Runs** → **Error message**, y el detalle en **Output logs** / **Error logs** (CloudWatch).

### 3. Verificar

- **Output logs** de la ejecución: el reporte JSON impreso, con `"rows_in_equal_rows_out": true`.
- En S3:
  - `trusted/vehiculos/` con las carpetas `anio=2022` … `anio=2026`;
  - `logs/trusted_2026-11-16.json` con el reporte de calidad.

## Evidencias

Archivos en `04_glue_spark/evidencias/`:

- [`01_job_detalles.png`](evidencias/01_job_detalles.png): Job details (LabRole, Spark, Glue 6.0, G.1X)
- [`02_job_succeeded.png`](evidencias/02_job_succeeded.png): ejecución **Succeeded**, 2 min 11 s, 2 workers, 0,073 DPU-hora
- [`03_trusted_consola.png`](evidencias/03_trusted_consola.png): `trusted/vehiculos/` en la consola con las particiones `anio=2022` … `anio=2026`
- [`04_trusted_terminal.png`](evidencias/04_trusted_terminal.png): archivos Parquet por año (`aws s3 ls --recursive`). Hay varios por año porque Spark escribe en paralelo
- [`05_reporte_archivo.png`](evidencias/05_reporte_archivo.png): reporte de calidad `logs/trusted_2026-11-16.json` descargado
- [`06_reporte_terminal.png`](evidencias/06_reporte_terminal.png): el mismo reporte desde la terminal, con `"rows_in_equal_rows_out": true`

## Costos

Glue cobra por DPU-hora (~0,44 USD). La ejecución real usó **0,073 DPU-hora ≈ 0,03 USD**. No queda nada encendido después del job.
