# Punto 2 — Fuentes de datos (RDS MariaDB, archivo en EC2, URL)

## 2.1 Snapshot local

### Qué hace `descargar_snapshot.py`

1. Lee los metadatos del dataset y **aborta si las 9 columnas cambiaron**.
2. Pide al servidor el total y los conteos de cada fuente (no hay ningún total fijo en el código).
3. Descarga páginas de 50.000 filas con `$order=:id`. `:id` es el identificador interno de fila de Socrata: con orden fijo, `$offset` siempre recorre la misma secuencia, sin saltos ni repeticiones. Se guarda como columna `socrata_row_id` (clave técnica de carga, **no** es un id de accidente).
4. Reparte cada fila por igualdad exacta del departamento: Antioquia y Bogotá D.C. se escriben en su CSV; las del resto solo se cuentan, porque esa fuente es la URL que se consulta en vivo.
5. Vuelve a consultar metadatos y conteos: si el dataset cambió durante la descarga, falla y pide repetir.
6. Escribe `manifest.json` con conteos, filtros SoQL, NULL por columna, SHA-256 y el resultado de cada comprobación; copia el manifiesto a `evidencias/`.

Los NULL se conservan: en el CSV un NULL es un campo vacío. No se eliminan duplicados ni filas.

### Cómo ejecutarlo

Desde la raíz del repositorio (Python 3.9 o superior, sin instalar nada):

```bash
python3 02_fuentes/scripts/descargar_snapshot.py
```

Tarda alrededor de 1 minuto.

### Archivos producidos

En `02_fuentes/data/snapshot_<AAAAMMDDTHHMMSSZ>/`:

| Archivo | Uso | Filas (corte 2026-11-15) |
|---|---|---:|
| `fuente_rds_antioquia.csv` | se carga en RDS MariaDB | 175.618 |
| `fuente_ec2_bogota.csv` | se copia a la instancia EC2 | 62.990 |
| `manifest.json` | conteos, hashes y comprobaciones | — |

Formato: UTF-8, separador coma, encabezado, fin de línea `\n`. Columna 1 `socrata_row_id` y luego las 9 columnas originales.

### Cómo sé que funcionó

1. La salida termina en `Todas las comprobaciones pasaron.` y el código de salida es 0.
2. En `manifest.json`, `all_checks_passed` es `true` y `local_counts` coincide con `server_counts_before` y `server_counts_after`.
3. Conteo rápido de líneas: `wc -l` da filas + 1 por el encabezado.

Resultado real: [`evidencias/manifest_snapshot_20261115T221648Z.json`](evidencias/manifest_snapshot_20261115T221648Z.json). Total 450.335 filas, 9 comprobaciones OK, 20 NULL en `edad_vehiculo` y 0 en las demás.

Para comprobar que la descarga es reproducible, basta con ejecutarla otra vez y comparar el `sha256` de los dos manifiestos: si el dataset no se actualizó, los archivos son idénticos (se comprobó en este proyecto con dos descargas en días distintos).

**Si el origen se actualiza**, un nuevo snapshot tendrá otro total. Eso es correcto: el manifiesto documenta cada corte. Todas las fuentes en AWS deben cargarse **desde el mismo snapshot** y se debe anotar su `snapshot_id`.

## 2.2 Fuente URL (resto de Colombia)

La fuente URL es la API pública consultada en vivo, con el filtro:

```sql
departamento_accidente NOT IN ('ANTIOQUIA', 'BOGOTA D.C.') OR departamento_accidente IS NULL
```

(`IS NULL` evita perder filas sin departamento; hoy son 0, pero así las tres fuentes siempre suman el total.)

```bash
cd 02_fuentes/scripts
python3 socrata_api.py conteos     # conteos en vivo por fuente y si suman el total
python3 socrata_api.py url-resto   # URL corta (5 filas, JSON) para abrir en el navegador y tomar la captura
```

**Uso en el punto 3:** la ingesta llama a `socrata_api.fetch_remainder_rows()`, que lee todas las páginas de esta URL en vivo, y compara las filas descargadas con el conteo que da el servidor en ese momento. Si no coinciden, lo registra en el log.

## 2.3 Archivo CSV en EC2 (Bogotá)

Cuenta usada: **AWS Academy Learner Lab**, región `us-east-1`. La misma EC2 se usará después como cliente para cargar RDS, así RDS no necesita acceso público.

1. **Crear la instancia** en la consola de AWS:
   - Amazon Linux 2023, tipo `t3.micro`.
   - Par de claves: `vockey`. El archivo `labsuser.pem` se descarga desde **"AWS Details"** en el Learner Lab.
   - Security Group: permitir SSH (puerto 22) **solo desde tu IP**. **No uses la opción "My IP"**: puede tomar tu dirección IPv6, y como la EC2 solo tiene IPv4 pública, la conexión SSH da *timeout*. Escribe a mano tu IPv4 seguida de `/32` (la obtienes con `curl -4 ifconfig.me`). Si cambias de red, tu IPv4 cambia y hay que actualizar esta regla.
   - En "Advanced details", **IAM instance profile: `LabInstanceProfile`**. Le da a la EC2 permiso para usar otros servicios (en el punto 3 escribirá en S3) y permite abrir su terminal desde el navegador.

2. **Copiar el CSV** desde tu computador, en la **raíz del proyecto**. `<EC2_PUBLIC_DNS>` es la dirección de la EC2 que muestra la consola; **cambia en cada sesión del lab**.

   ```bash
   chmod 400 ~/Downloads/labsuser.pem
   ssh -i ~/Downloads/labsuser.pem ec2-user@<EC2_PUBLIC_DNS> "mkdir -p ~/fuentes/bogota ~/carga"
   scp -i ~/Downloads/labsuser.pem \
     02_fuentes/data/snapshot_20261115T221648Z/fuente_ec2_bogota.csv \
     ec2-user@<EC2_PUBLIC_DNS>:~/fuentes/bogota/
   ```

3. **Verificar dentro de la EC2** que el archivo llegó idéntico:

   ```bash
   ssh -i ~/Downloads/labsuser.pem ec2-user@<EC2_PUBLIC_DNS>
   sha256sum ~/fuentes/bogota/fuente_ec2_bogota.csv
   # esperado: 988074497c05ef7cd30ca789ee2e9e09f8a0722256abdbb30409f955439e0362
   tail -n +2 ~/fuentes/bogota/fuente_ec2_bogota.csv | wc -l
   # esperado: 62990
   ```

   Los valores esperados son del snapshot del corte 2026-11-15; con otro snapshot, salen de `files.ec2_bogota` en su manifiesto.

4. **Evidencias:**
   - captura de la instancia en estado "Running" en la consola;
   - captura de la terminal con los dos comandos del paso 3 y sus resultados.

## 2.4 RDS MariaDB (Antioquia)

Requiere que la EC2 de la sección 2.3 ya exista: la carga se hace desde ella.

1. **Crear la base** en la consola de RDS (región `us-east-1`):
   - Motor **MariaDB**, clase `db.t3.micro`, 20 GB, sin Multi-AZ.
   - Usuario maestro y contraseña: los eliges tú. La contraseña **no** se guarda en el repositorio.
   - **Sin acceso público.**
   - En "Additional configuration" → "Monitoring", **desmarcar "Enhanced monitoring"**: el Learner Lab no lo permite y la creación falla.
   - En "Connectivity", elegir **"Connect to an EC2 compute resource"** y seleccionar la EC2 de la sección 2.3. AWS configura solo el permiso del puerto 3306 entre las dos.
   - Cuando el estado sea "Available", copiar el **endpoint** de la base (`<RDS_ENDPOINT>`).

2. **Copiar el CSV de Antioquia y los 3 SQL a la EC2**, desde la raíz del proyecto en tu computador:

   ```bash
   scp -i ~/Downloads/labsuser.pem \
     02_fuentes/data/snapshot_20261115T221648Z/fuente_rds_antioquia.csv \
     02_fuentes/sql/*.sql \
     ec2-user@<EC2_PUBLIC_DNS>:~/carga/
   ```

3. **Cargar desde la EC2.** La base exige conexión cifrada (`require_secure_transport=ON`); sin cifrado responde `ERROR 3159 ... insecure transport are prohibited`. Por eso se descarga el certificado oficial de AWS y se usa en cada conexión: el cliente cifra la conexión y verifica que el servidor sea realmente la base de RDS.

   ```bash
   ssh -i ~/Downloads/labsuser.pem ec2-user@<EC2_PUBLIC_DNS>
   sudo dnf install -y mariadb105          # cliente mysql
   cd ~/carga
   curl -o global-bundle.pem https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem

   # Variables para no repetir textos largos (duran mientras esté abierta la sesión SSH)
   RDS=<RDS_ENDPOINT>
   SSL="--ssl-ca=global-bundle.pem --ssl-verify-server-cert"

   mysql $SSL -h $RDS -u admin -p < 01_crear_tabla.sql
   mysql $SSL --local-infile=1 -h $RDS -u admin -p < 02_cargar_antioquia.sql
   mysql $SSL -h $RDS -u admin -p -t < 03_verificar_carga.sql | tee rds_verificacion.txt
   rm ~/carga/fuente_rds_antioquia.csv     # la fuente de archivos en EC2 es solo Bogotá
   ```

   El endpoint aparece en la consola, en la base → pestaña "Conectividad y seguridad", dentro del comando de ejemplo `mysql -h ...`. Cada `mysql -p` pide la contraseña (no se ve al escribirla).

4. **Cómo sé que funcionó:** los resultados coinciden con los valores esperados escritos en los comentarios de `03_verificar_carga.sql` (corte 2026-11-15: 175.618 filas, solo `ANTIOQUIA`, `edad_null` = 5, `edad_cero` = 251, `modelo_null` = 0).

5. **Evidencias:** traer el archivo de verificación a tu computador, desde la raíz del proyecto:

   ```bash
   scp -i ~/Downloads/labsuser.pem ec2-user@<EC2_PUBLIC_DNS>:~/carga/rds_verificacion.txt 02_fuentes/evidencias/
   ```

   Y tomar dos capturas: la base en estado "Available" en la consola, y la terminal con la salida de `03_verificar_carga.sql`.

## Costos

- RDS y EC2 cobran mientras están encendidas. Al terminar cada sesión, detener RDS a mano (el Learner Lab puede no detenerla) y la EC2. AWS vuelve a encender sola una RDS detenida a los 7 días.
- Al iniciar una sesión, el Learner Lab enciende la EC2 sola: si no se va a usar, detenerla.

## Evidencias

Archivos en `02_fuentes/evidencias/`:

- [`manifest_snapshot_20261115T221648Z.json`](evidencias/manifest_snapshot_20261115T221648Z.json): manifiesto del snapshot
- [`01_descarga_snapshot.png`](evidencias/01_descarga_snapshot.png): salida de `descargar_snapshot.py` con las 9 comprobaciones en OK
- [`02_url_resto.png`](evidencias/02_url_resto.png): URL del resto abierta en el navegador
- [`03_ec2_running.png`](evidencias/03_ec2_running.png): instancia EC2 en estado "Running" en la consola
- [`04_ec2_verificacion.png`](evidencias/04_ec2_verificacion.png): terminal de la EC2 con `sha256sum` y el conteo de filas
- [`05_rds_available.png`](evidencias/05_rds_available.png): base RDS en estado "Available" en la consola
- [`06_rds_verificacion.png`](evidencias/06_rds_verificacion.png): terminal con la salida de `03_verificar_carga.sql`
- [`rds_verificacion.txt`](evidencias/rds_verificacion.txt): salida de `03_verificar_carga.sql` en texto
