# Punto 6 — Consultas SQL con Athena, EMR/Hive y Spark SQL

## Qué hace

Las 5 preguntas de negocio se responden con **6 consultas SQL** (la pregunta 1 se divide en departamentos y municipios). Las mismas consultas, **sin cambios**, se ejecutan en tres motores sobre la tabla `siniestros.vehiculos` del Glue Data Catalog (punto 5). Si los tres dan los mismos números, el catálogo y los datos son consistentes.

| Archivo | Pregunta | Qué calcula |
|---|---|---|
| `consultas/q1a_departamentos.sql` | 1 | Vehículos por departamento y % del total |
| `consultas/q1b_municipios.sql` | 1 | Top 15 municipios (con su departamento) |
| `consultas/q2_tipos_vehiculo.sql` | 2 | Vehículos por tipo y % del total |
| `consultas/q3_evolucion_mensual.sql` | 3 | Vehículos por año y mes |
| `consultas/q4_proporcion_mortal.sql` | 4 | % de registros `CON MUERTOS` por tipo (tipos con ≥ 500 registros) |
| `consultas/q5_antiguedad_gravedad.sql` | 5 | % de registros `CON MUERTOS` por rango de edad |

## Decisiones metodológicas

- Se cuentan **vehículos involucrados** (una fila = un vehículo), nunca accidentes.
- **Q3:** 07/2024 es un valor atípico alto y 08/2026–09/2026 parecen incompletos. Se informan; no se borran.
- **Q4:** solo tipos con **al menos 500 registros**. Con pocos registros la proporción engaña (un buldozer con 1 registro mortal daría 100 %). Quedan 11 tipos, que concentran casi todos los datos. Es una proporción de registros, **no** una tasa de mortalidad de ocupantes.
- **Q5:** rangos 0–5, 6–10, 11–15, 16–20, 21–30 y más de 30 años. Se excluyen las 20 edades NULL y las 65 marcadas fuera de rango en el punto 4. Es una relación **descriptiva**, no causal.

## Compatibilidad entre motores

Las consultas evitan diferencias conocidas entre Athena (Trino), Hive y Spark SQL:
- `100.0 * x / y` en vez de `100 * x / y`: en Athena, entero ÷ entero es división entera.
- Porcentaje del total con `SUM(COUNT(*)) OVER ()` (función de ventana), soportada por los tres.
- Q5 calcula el rango en una subconsulta, porque Hive no permite `GROUP BY` sobre un alias.
- Las etiquetas de rango llevan un prefijo (`01)`, `02)`...) para que se ordenen bien y no usan `ñ`.
- No se filtra por `anio`: el crawler puede registrarlo como texto o como número.

## Resultados esperados (prueba local con Spark SQL, datos del 2026-11-16)

**Q1a (top 5):** ANTIOQUIA 175.618 (39,00 %) · BOGOTA D.C. 62.990 (13,99 %) · VALLE DEL CAUCA 56.503 (12,55 %) · SANTANDER 19.595 · ATLANTICO 14.997. Total: 31 departamentos.

**Q1b (top 5):** MEDELLIN 111.235 · BOGOTA 62.990 · CALI 34.531 · BARRANQUILLA 13.589 · BELLO 10.693.

**Q2 (top 5):** MOTOCICLETA 255.266 (56,68 %) · AUTOMOVIL 99.900 (22,18 %) · CAMIONETA 38.438 (8,54 %) · BUS 17.439 · CAMION 12.274. Total: 31 tipos.

**Q3:** 57 meses, de 2022-01 (8.331) a 2026-09; 2024-07 = 28.854.

**Q4:**

| Tipo | Vehículos | Con muertos | % |
|---|---:|---:|---:|
| TRACTOCAMION | 5.797 | 1.667 | 28,76 |
| VOLQUETA | 2.221 | 435 | 19,59 |
| CAMION | 12.274 | 2.225 | 18,13 |
| MOTOCARRO | 1.048 | 68 | 6,49 |
| MICROBUS | 4.813 | 303 | 6,30 |
| CAMPERO | 9.691 | 569 | 5,87 |
| BUS | 17.439 | 965 | 5,53 |
| BUSETA | 3.168 | 168 | 5,30 |
| CAMIONETA | 38.438 | 2.002 | 5,21 |
| MOTOCICLETA | 255.266 | 12.958 | 5,08 |
| AUTOMOVIL | 99.900 | 2.515 | 2,52 |

**Q5:**

| Rango de edad | Vehículos | Con muertos | % |
|---|---:|---:|---:|
| 0–5 | 121.689 | 6.410 | 5,27 |
| 6–10 | 124.514 | 5.688 | 4,57 |
| 11–15 | 112.794 | 5.967 | 5,29 |
| 16–20 | 58.643 | 3.167 | 5,40 |
| 21–30 | 22.144 | 1.569 | 7,09 |
| más de 30 | 10.466 | 1.088 | 10,40 |

Suma: 450.250 = 450.335 − 20 NULL − 65 fuera de rango.

## Paso a paso en AWS

### 1. Athena (no necesita EMR)

1. Consola → **Athena** → **Query editor**. La primera vez pide una ubicación de resultados: **Settings** → **Manage** → `s3://proyecto2-siniestros/athena-results/` → **Save**.
2. Data source: **AwsDataCatalog**. Database: **siniestros**.
3. Pegar cada consulta de `consultas/` y **Run**. Comparar con los resultados esperados.

### 2. Hive y Spark SQL (en EMR)

Con el clúster del punto 5 en estado Waiting, desde tu computador en la raíz del proyecto:

```bash
ssh -i ~/Downloads/labsuser.pem hadoop@<EMR_PRIMARY_DNS> "mkdir -p ~/punto6"
scp -i ~/Downloads/labsuser.pem -r \
  06_sql_analitico/consultas 06_sql_analitico/ejecutar_consultas_emr.sh \
  hadoop@<EMR_PRIMARY_DNS>:~/punto6/
```

En el nodo principal:

```bash
cd ~/punto6
bash ejecutar_consultas_emr.sh
```

Ejecuta las 6 consultas en **Hive** y en **Spark SQL**, muestra los resultados y los guarda en `~/resultados/` y en `s3://proyecto2-siniestros/refined/sql/`. Tarda varios minutos: cada consulta arranca su propio proceso.

## Evidencias

Archivos en `06_sql_analitico/evidencias/`:

- `01_athena_q1a.png` … `06_athena_q5.png`: cada consulta en Athena con su resultado. Athena analizó solo 258 KB (Q4) y 418 KB (Q5) de los 9,3 MB de la tabla: Parquet guarda los datos por columnas y Athena lee solo las columnas que usa la consulta
- [`07_resultados_consultas.png`](evidencias/07_resultados_consultas.png): Q4 y Q5 en **Hive** y en **Spark SQL** (EMR), con los mismos números que Athena
- [`08_refined_sql.png`](evidencias/08_refined_sql.png): `refined/sql/` en S3 con las 12 salidas (6 de Hive y 6 de Spark SQL). Los tamaños son idénticos entre motores
