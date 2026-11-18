# Punto 5 — Catalogación de tablas con AWS Glue y EMR/Hive

## Qué es catalogar

Los datos de `trusted/vehiculos/` son archivos Parquet en S3. Para consultarlos con SQL, un motor necesita saber **qué tabla son**: dónde están, qué columnas tienen, de qué tipo y cómo están particionados. Esa descripción se guarda en un **catálogo** (metastore).

El **AWS Glue Data Catalog** es ese catálogo. Athena, Hive y Spark (en EMR) leen el mismo catálogo, así que la tabla se define una sola vez y la usan los tres motores.

```text
trusted/vehiculos/ (Parquet) ──Glue Crawler──> Glue Data Catalog: siniestros.vehiculos
                                                   │            │             │
                                                Athena      EMR/Hive     EMR/Spark SQL
```

## Parte A — Glue: el crawler crea la tabla

Un **crawler** recorre una carpeta de S3, lee los archivos y crea la tabla con sus columnas, tipos y particiones.

1. Consola → **AWS Glue** → **Data Catalog** → **Databases** → **Add database**. Name: `siniestros`. **Create database**.
2. **Data Catalog** → **Crawlers** → **Create crawler**:
   - Name: `crawler_trusted`. **Next**.
   - **Add a data source** → S3 → path `s3://proyecto2-siniestros/trusted/vehiculos/` → "Crawl all sub-folders". **Add an S3 data source** → **Next**.
   - IAM role: **LabRole**. **Next**.
   - Target database: `siniestros`. Crawler schedule: **On demand**. **Next** → **Create crawler**.
3. **Run crawler**. Tarda alrededor de 1 minuto; el estado vuelve a "Ready" y "Last run" dice **Succeeded**.
4. **Data Catalog** → **Tables**: aparece la tabla **`vehiculos`** en la base `siniestros`: 15 columnas, con `anio` como partición.

   Resultado real: el crawler detectó bien los tipos (`modelo_vehiculo`, `edad_vehiculo` y `mes` como `int`; `edad_fuera_rango` como `boolean`) y registró la partición `anio` como `string`, porque la toma del nombre de la carpeta. Por eso las consultas del punto 6 no filtran por `anio`.

El crawler nombra la tabla como la carpeta (`vehiculos`). Las consultas del punto 6 usan `siniestros.vehiculos`.

## Parte B — EMR/Hive: la misma tabla desde Hive

### Crear el clúster EMR (se usa también en los puntos 6 y 7)

EMR **no sobrevive al fin de la sesión del Learner Lab**. Crear el clúster solo cuando todo esté listo y hacer los puntos 5B, 6 y 7 en la misma sesión.

Consola → **EMR** → **Create cluster**:

| Campo | Valor |
|---|---|
| Name | `proyecto2-emr` |
| Amazon EMR release | la más reciente `emr-7.x` |
| Application bundle | **Custom**: marcar **Hadoop, Hive, Spark** |
| AWS Glue Data Catalog settings | marcar **Use for Hive table metadata** y **Use for Spark table metadata** |
| Cluster configuration | Instance groups. Primary: **m4.large**. Core: **m4.large**, 1 instancia. **Quitar el grupo Task** |
| Cluster termination | **Automatically terminate cluster after idle time**: 1 hora (protección por si se olvida) |
| Cluster logs | Si da error de bucket: desmarcar "Publish cluster-specific logs to Amazon S3" |
| Security configuration and EC2 key pair | **vockey** |
| Amazon EMR service role | Choose existing: **EMR_DefaultRole** |
| EC2 instance profile for Amazon EMR | Choose existing: **EMR_EC2_DefaultRole** |

**Recomendado para evitar el problema descrito más abajo:** en **Software settings** (Configuración de software), pegar el JSON de la sección siguiente antes de crear el clúster.

**Create cluster**. Tarda 10–15 minutos hasta el estado **Waiting** (listo).

### Comprobar que Hive y Spark usan el Glue Data Catalog

En el clúster → pestaña **Configuraciones** → **Configuraciones del clúster** deben aparecer **dos** clasificaciones con `hive.metastore.client.factory.class = com.amazonaws.glue.catalog.metastore.AWSGlueDataCatalogHiveClientFactory`:
- `hive-site` (Hive)
- `spark-hive-site` (Spark)

**Lo que pasó en este proyecto:** aunque se marcaron las dos casillas, el clúster se creó solo con `spark-hive-site`. Hive buscaba entonces su catálogo local y fallaba con `Could not connect to meta store ... Connection refused`, mientras que `spark-sql -e "SHOW TABLES IN siniestros"` sí mostraba `vehiculos`.

**Corrección sin crear otro clúster** (EMR ≥ 5.21 permite reconfigurar un clúster en ejecución): en **Configuración del grupo de instancias** → seleccionar el grupo **Principal** → **Volver a configurar** → editar en JSON → pegar:

```json
[
  {
    "Classification": "hive-site",
    "Properties": {
      "hive.metastore.client.factory.class": "com.amazonaws.glue.catalog.metastore.AWSGlueDataCatalogHiveClientFactory"
    }
  },
  {
    "Classification": "spark-hive-site",
    "Properties": {
      "hive.metastore.client.factory.class": "com.amazonaws.glue.catalog.metastore.AWSGlueDataCatalogHiveClientFactory"
    }
  }
]
```

Repetir con el grupo **Central** si no se aplicó a todos. Esperar a que los grupos vuelvan a **En ejecución** y comprobar en el nodo principal:

```bash
grep -A1 "metastore.client.factory" /etc/hive/conf/hive-site.xml   # debe mostrar AWSGlueDataCatalogHiveClientFactory
```

### Permitir SSH al nodo principal

Clúster → pestaña **Properties** (o Summary) → **EC2 security groups** → grupo del nodo **Primary** (`ElasticMapReduce-master`) → **Edit inbound rules** → **Add rule**:
- Type: **SSH**. Source: **Custom**, tu IPv4 con `/32` (`curl -4 ifconfig.me`). **No uses "My IP"** (puede tomar la IPv6).

Copiar el **Primary node public DNS** del clúster. En EMR el usuario es **`hadoop`**, no `ec2-user`:

```bash
ssh -i ~/Downloads/labsuser.pem hadoop@<EMR_PRIMARY_DNS>
```

### Verificar la tabla en Hive

En el nodo principal:

```bash
hive -e "SHOW DATABASES; SHOW TABLES IN siniestros; DESCRIBE siniestros.vehiculos; SELECT COUNT(*) FROM siniestros.vehiculos;"
```

Resultado esperado: aparece `siniestros`, la tabla `vehiculos`, sus columnas (`anio` como partición) y `450335`. Esto demuestra que **Hive usa el Glue Data Catalog**: la tabla la creó el crawler, no Hive.

## Evidencias

Archivos en `05_catalogacion/evidencias/`:

- [`01_crawler_succeeded.png`](evidencias/01_crawler_succeeded.png): el crawler con "Last run: Succeeded"
- [`02_tabla_glue.png`](evidencias/02_tabla_glue.png): la tabla `vehiculos` en Glue (15 columnas, partición `anio`)
- [`03_emr_comenzando.png`](evidencias/03_emr_comenzando.png): el clúster `proyecto2-emr` en la consola de EMR (capturado mientras arrancaba)
- [`04_hive_catalogo.png`](evidencias/04_hive_catalogo.png): Hive en EMR con `SHOW DATABASES`, `SHOW TABLES`, `DESCRIBE` y el conteo 450335, leyendo el Glue Data Catalog

## Costos

- Crawler: centavos por ejecución.
- EMR (2 × m4.large): ~0,20 USD/hora por nodo. **Terminar el clúster** (Terminate) al acabar los puntos 6 y 7.
