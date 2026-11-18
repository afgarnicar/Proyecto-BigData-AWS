# Punto 7 — Análisis descriptivo con PySpark

## Qué hace

`scripts/analisis_pyspark.py` responde las **mismas 5 preguntas** del punto 6, pero con la **API de DataFrames** de Spark en Python (`groupBy`, `agg`, `filter`, `orderBy`), sin escribir SQL. Es la misma lógica expresada de otra forma; los resultados deben coincidir con los del punto 6.

- Lee directamente `trusted/vehiculos/` (Parquet).
- Imprime cada resultado.
- Guarda cada uno en la zona **refined** del data lake, un CSV por pregunta:

```text
s3://proyecto2-siniestros/refined/pyspark/
├── q1a_departamentos/part-....csv
├── q1b_municipios/part-....csv
├── q2_tipos_vehiculo/part-....csv
├── q3_evolucion_mensual/part-....csv
├── q4_proporcion_mortal/part-....csv
└── q5_antiguedad_gravedad/part-....csv
```

Estos resultados son los que consume la aplicación del punto 8.

## Equivalencia SQL ↔ PySpark

| SQL (punto 6) | PySpark (punto 7) |
|---|---|
| `GROUP BY tipo_vehiculo` + `COUNT(*)` | `.groupBy("tipo_vehiculo").agg(F.count("*"))` |
| `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` | `F.sum(F.when(..., 1).otherwise(0))` |
| `HAVING COUNT(*) >= 500` | `.filter(F.col("vehiculos") >= 500)` |
| `SUM(COUNT(*)) OVER ()` | `F.sum(...).over(Window.partitionBy())` |
| `ORDER BY ... DESC` / `LIMIT 15` | `.orderBy(F.desc(...))` / `.limit(15)` |

## Resultado de la prueba local

Mismos números que las consultas SQL del punto 6 (ver la tabla de resultados esperados en `06_sql_analitico/README.md`): 450.335 vehículos en trusted; Q4 encabezada por TRACTOCAMION (28,76 %); Q5 de 4,57 % (6–10 años) a 10,40 % (más de 30 años). La única diferencia visual es de formato: PySpark muestra `6.3` donde SQL muestra `6.30`.

## Paso a paso en AWS (en el clúster EMR del punto 5)

Desde tu computador, en la raíz del proyecto:

```bash
scp -i ~/Downloads/labsuser.pem 07_pyspark/scripts/analisis_pyspark.py hadoop@<EMR_PRIMARY_DNS>:~/
```

En el nodo principal:

```bash
PYTHONUNBUFFERED=1 spark-submit analisis_pyspark.py 2>/dev/null | tee resultados_pyspark.txt
aws s3 ls s3://proyecto2-siniestros/refined/pyspark/ --recursive --human-readable
```

- `2>/dev/null` oculta los mensajes internos de Spark para que se lean los resultados.
- `PYTHONUNBUFFERED=1` hace que cada resultado aparezca apenas se calcula. Sin esto, al pasar por `| tee` Python retiene la salida y la pantalla puede quedar en blanco varios minutos aunque el script esté trabajando (pasó en este proyecto).
- Para otro bucket: `spark-submit analisis_pyspark.py --LAKE s3://<bucket>`.

## Evidencias

Archivos en `07_pyspark/evidencias/`:

- [`01_pyspark_q1a.png`](evidencias/01_pyspark_q1a.png): `spark-submit` en EMR, total 450.335 y departamentos
- [`02_pyspark_q1b.png`](evidencias/02_pyspark_q1b.png): municipios
- [`03_pyspark_q2.png`](evidencias/03_pyspark_q2.png): tipos de vehículo
- [`04_pyspark_q3.png`](evidencias/04_pyspark_q3.png): evolución mensual (se ve el pico de 07/2024 = 28.854)
- [`05_pyspark_q4_q5.png`](evidencias/05_pyspark_q4_q5.png): proporción mortal por tipo y por antigüedad
- [`06_refined_pyspark.png`](evidencias/06_refined_pyspark.png): `refined/pyspark/` en S3 con un CSV por pregunta
