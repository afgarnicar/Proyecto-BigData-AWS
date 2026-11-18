# Punto 3 — Ingesta automática a S3

## Qué hace

Un script de Python en la EC2 (`ingesta_s3.py`) lee las tres fuentes del punto 2 y deja una copia de cada una en la zona `raw/` del data lake. `cron` lo ejecuta automáticamente cada hora.

```text
                    ┌──────────── EC2 proyecto2-ec2 ─────────────┐
RDS (Antioquia) ───>│                                            │
CSV local (Bogotá) >│  ingesta_s3.py  (lo ejecuta cron cada hora) │──> S3 raw/ + logs/
API URL (resto) ───>│                                            │
                    └────────────────────────────────────────────┘
```

## Organización del bucket

```text
s3://proyecto2-siniestros/
├── raw/                                   ← punto 3: datos tal como vienen de cada fuente
│   ├── rds/fecha_ingesta=2026-11-16/vehiculos_antioquia.csv
│   ├── ec2/fecha_ingesta=2026-11-16/vehiculos_bogota.csv
│   └── url/fecha_ingesta=2026-11-16/vehiculos_resto.json
├── trusted/                               ← punto 4: datos limpios en Parquet
├── refined/                               ← puntos 6 a 8: resultados de consultas
└── logs/ingesta_2026-11-16_10-00-00.json  ← resumen de cada ejecución (hora de Colombia)
```

- `raw/` está separado por fuente, para que se vea de dónde viene cada dato.
- `fecha_ingesta=AAAA-MM-DD` es el formato `nombre=valor` que Glue y Athena reconocen como columna. Si el script corre varias veces el mismo día, sobrescribe los archivos de ese día: no duplica datos.
- **Cada fuente queda en el formato en que llega**, como corresponde a la zona `raw`:
  - RDS y EC2 en **CSV**, con 10 columnas (`socrata_row_id` + las 9 del dataset);
  - URL en **JSON Lines** (un registro JSON por línea), tal como lo entrega la API. Un campo NULL no aparece en el registro, igual que en la API. Único cambio: `:id` se guarda como `socrata_row_id`, porque los `:` dan problemas en Spark y SQL.

  La estandarización a un solo formato (Parquet) se hace en el punto 4.
- Los logs están fuera de `raw/` para que Glue no los confunda con datos.

## Decisiones

- **Por qué cron en la EC2:** la EC2 ya llega a las tres fuentes (está en la red privada de RDS, tiene el CSV y sale a internet). Una Lambda que llegara a RDS necesitaría estar en la red privada y un NAT Gateway (≈1 USD/día) para salir a internet.
- **Limitación:** cron solo corre mientras la EC2 está encendida, es decir, durante las sesiones del Learner Lab.
- **Permisos:** la EC2 escribe en S3 gracias a `LabInstanceProfile`. No hay claves de AWS en el código.
- **Secretos:** la contraseña de RDS está solo en `~/ingesta/.env` dentro de la EC2 (permisos `600`). En el repositorio solo está la plantilla `ingesta.env.example`.
- **Si una fuente falla** (por ejemplo, RDS detenida), el error queda en el log y las otras dos se ingieren igual.

## Paso a paso en AWS

### 1. Encender lo necesario

- Iniciar el Learner Lab. La EC2 se enciende sola; copiar su DNS nuevo.
- Encender RDS: Bases de datos → `proyecto2-mariadb` → Acciones → Iniciar. Esperar a "Disponible".

### 2. Crear el bucket

Consola → **S3** → **Crear bucket**:
- Tipo: **Uso general**. Región: **us-east-1**.
- Nombre: `proyecto2-siniestros`. Si está ocupado, agregar un sufijo corto (`proyecto2-siniestros-andres`) y usar ese nombre en el `.env`.
- **Bloquear todo el acceso público:** dejarlo activado.
- Lo demás, por defecto. **Crear bucket**.

### 3. Copiar los scripts a la EC2

Desde la raíz del proyecto en tu computador:

```bash
ssh -i ~/Downloads/labsuser.pem ec2-user@<EC2_PUBLIC_DNS> "mkdir -p ~/ingesta"
scp -i ~/Downloads/labsuser.pem \
  03_ingesta_s3/scripts/ingesta_s3.py \
  02_fuentes/scripts/socrata_api.py \
  03_ingesta_s3/ingesta.env.example \
  ec2-user@<EC2_PUBLIC_DNS>:~/ingesta/
```

### 4. Preparar la EC2

```bash
ssh -i ~/Downloads/labsuser.pem ec2-user@<EC2_PUBLIC_DNS>

# Librerías: boto3 (S3) y pymysql (MariaDB)
sudo dnf install -y python3-pip
pip3 install --user boto3 pymysql

# Configuración: completar RDS_HOST, RDS_PASSWORD y, si cambió, S3_BUCKET
cd ~/ingesta
cp ingesta.env.example .env
chmod 600 .env          # solo tu usuario puede leerlo
nano .env               # Ctrl+O para guardar, Ctrl+X para salir
```

El certificado `global-bundle.pem` ya está en `~/carga/` desde el punto 2 (`RDS_SSL_CA` apunta ahí).

### 5. Probar a mano

```bash
python3 ~/ingesta/ingesta_s3.py
```

Resultado esperado (los conteos de URL pueden cambiar si el dataset se actualiza):

```text
  [OK] rds: ... 'rows': 175618, 'expected_rows': 175618 ...
  [OK] ec2: ... 'rows': 62990, 'expected_rows': 62990 ...
  [OK] url: ... 'rows': 211727, 'expected_rows': 211727 ...   (archivo .json)
Ingesta completa: las 3 fuentes quedaron en raw/.
```

Tarda unos 2 minutos (la fuente URL descarga 211 mil filas de la API).

### 6. Programar cron (la parte automática)

Amazon Linux 2023 no trae cron instalado:

```bash
sudo dnf install -y cronie
sudo systemctl enable --now crond
```

Agregar la tarea (cada hora, en el minuto 0):

```bash
(crontab -l 2>/dev/null; echo "0 * * * * /usr/bin/python3 /home/ec2-user/ingesta/ingesta_s3.py >> /home/ec2-user/ingesta/ingesta.log 2>&1") | crontab -
crontab -l
```

La línea se lee así: `0 * * * *` = "en el minuto 0 de cada hora, todos los días"; `>> ingesta.log 2>&1` guarda la salida y los errores en un archivo local.

### 7. Verificar la ejecución automática

Después de la siguiente hora en punto:

```bash
tail -n 8 ~/ingesta/ingesta.log
aws s3 ls s3://proyecto2-siniestros/ --recursive --human-readable
```

Debe aparecer un log nuevo en `logs/` con la hora en punto (por ejemplo `ingesta_2026-11-16_14-00-00.json`), que demuestra que corrió sin intervención.

## Evidencias

Archivos en `03_ingesta_s3/evidencias/`:

- [`01_bucket_contenido.png`](evidencias/01_bucket_contenido.png): `aws s3 ls` con las zonas `raw/` y `logs/`, los 3 archivos de datos y los logs
- [`02_consola_buckets.png`](evidencias/02_consola_buckets.png): el bucket `proyecto2-siniestros` en la consola de S3
- [`03_consola_raw.png`](evidencias/03_consola_raw.png): `raw/` en la consola, separado por fuente (`ec2/`, `rds/`, `url/`)
- [`04_ejecucion_manual.png`](evidencias/04_ejecucion_manual.png): ejecución a mano (12:49), las 3 fuentes en OK
- [`05_crontab.png`](evidencias/05_crontab.png): cron activado y la tarea programada (`crontab -l`)
- [`06_ejecucion_automatica.png`](evidencias/06_ejecucion_automatica.png): `ingesta.log` y el log de la ejecución de cron (13:00:03) con `"all_ok": true`
- [`07_consola_logs.png`](evidencias/07_consola_logs.png): `logs/` en la consola, con las ejecuciones manuales y la automática

## Costos

- S3: centavos por mes con este volumen (~100 MB por día de ingesta: el JSON de la URL pesa ~70 MB).
- RDS debe estar encendida para la ingesta. Al terminar la sesión, **detener RDS** y la EC2 (ver "Costos" en el README del punto 2).
