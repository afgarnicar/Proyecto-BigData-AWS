# Punto 8 — Visualización, Streamlit y API Gateway

## Arquitectura

```text
                          ┌─────────────────────────── AWS ───────────────────────────┐
Navegador ──> Streamlit (EC2, puerto 8501) ──HTTP──> API Gateway ──> Lambda ──> S3 refined/pyspark/
                                                     (HTTP API)    (api_resultados.py)
Tu computador ──> graficos.py (matplotlib) ──HTTP──> API Gateway  (misma API)
```

- **API Gateway + Lambda** exponen como una **API pública en JSON** los resultados de las 5 preguntas que PySpark guardó en `refined/` (punto 7).
- **Streamlit** es la aplicación que ve el usuario. Todos sus datos llegan por la API; no lee S3 directamente.
- **matplotlib** genera los gráficos estáticos para el documento, pidiendo los datos a la misma API.

**Por qué Streamlit no va "detrás" de API Gateway:** API Gateway no hospeda aplicaciones, y Streamlit necesita una conexión WebSocket permanente con el navegador que un proxy HTTP de API Gateway no transporta (la página quedaría en "Connecting..."). Por eso la aplicación está **expuesta mediante API Gateway** en el sentido de que consume sus datos a través de la API.

## La API

| Ruta | Respuesta |
|---|---|
| `GET /preguntas` | Lista de las 6 consultas (`id` y descripción) |
| `GET /resultados/{pregunta}` | `pregunta`, `descripcion`, `unidad`, `columnas` y `filas` |

`{pregunta}` es uno de: `q1a_departamentos`, `q1b_municipios`, `q2_tipos_vehiculo`, `q3_evolucion_mensual`, `q4_proporcion_mortal`, `q5_antiguedad_gravedad`. Cualquier otro valor responde **404**: la Lambda solo lee esas 6 carpetas de S3.

**Seguridad:** la API es pública y sin autenticación. Es aceptable porque solo entrega resultados **agregados** (conteos y porcentajes) de un dataset público, no registros individuales.

## Prueba local

- **Lambda:** ejecutada con un S3 simulado que lee los CSV reales de `refined/pyspark/`. `/preguntas` devuelve las 6; `/resultados/q4_proporcion_mortal` devuelve TRACTOCAMION 28.76, VOLQUETA 19.59…; `/resultados/q5_antiguedad_gravedad` devuelve 5.27 … 10.4; una pregunta inexistente devuelve 404.
- **Streamlit:** probada con `streamlit.testing` contra esa API simulada: las 6 páginas cargan sin errores.
- **matplotlib:** genera los 6 PNG. Los de la prueba se borraron; los de `graficos/` se generaron después con la API real.

## Paso a paso en AWS

### 1. Crear la Lambda

Consola → **Lambda** → **Event Functions** → **Create Event Function** (no "Funciones web": esas atienden la web sin API Gateway):
- **Crear desde cero**. Nombre: `api_resultados`. Versión ejecutable: **Python 3.12** o más reciente.
- **Configuración adicional** → rol de ejecución → **Usar un rol existente** → **LabRole**. Sin esto, Lambda intenta crear un rol nuevo, que el Learner Lab no permite y que no tendría permiso para leer S3.
- Lo demás, por defecto. **Create Event Function**.

Las otras funciones que aparecen en la lista (`RoleCreationFunction`, `ModLabRole`, etc.) son del Learner Lab: no tocarlas.

En **Código**: borrar el código de ejemplo del archivo `lambda_function.py`, pegar el contenido de `lambda/api_resultados.py` y **Deploy**. No hace falta renombrar nada: Lambda busca la función `lambda_handler`, que es la que define el archivo.

En **Configuración** → **Variables de entorno** → **Editar** → agregar clave `BUCKET`, valor `proyecto2-siniestros` → **Guardar**.

### 2. Crear la API en API Gateway

Consola → **API Gateway** → **Create API** → **HTTP API** → **Build**:
- **Integrations** → Add integration → **Lambda** → `api_resultados`. API name: `api-siniestros`. **Next**.
- **Configure routes**: dejar dos rutas, ambas con método **GET** y destino `api_resultados`:
  - `/preguntas`
  - `/resultados/{pregunta}`
- **Stages**: dejar `$default` con **Auto-deploy** activado. **Next** → **Create**.

Copiar la **Invoke URL** (algo como `https://abc123.execute-api.us-east-1.amazonaws.com`).

### 3. Probar la API

Abrir en el navegador:

```text
<INVOKE_URL>/preguntas
<INVOKE_URL>/resultados/q4_proporcion_mortal
```

Debe verse JSON con los mismos números de los puntos 6 y 7 (TRACTOCAMION 28.76…).

### 4. Streamlit en la EC2

1. Encender la EC2 `proyecto2-ec2` (si está detenida) y copiar su DNS público.
2. **Security Group** de la EC2 → **Edit inbound rules** → **Add rule**: Type **Custom TCP**, Port **8501**, Source **Anywhere-IPv4 (0.0.0.0/0)**. Abierto a cualquiera para poder mostrar la app desde otras redes; solo muestra datos agregados públicos.
3. Copiar la app a la EC2, desde la raíz del proyecto en tu computador:

   ```bash
   scp -i ~/Downloads/labsuser.pem 08_visualizacion/app.py ec2-user@<EC2_PUBLIC_DNS>:~/
   ```

4. En la EC2:

   ```bash
   pip3 install --user streamlit requests
   pkill -f "streamlit run"   # detiene una ejecución anterior, si la hay
   API_URL=<INVOKE_URL> nohup ~/.local/bin/streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true > streamlit.log 2>&1 &
   ```

   - `API_URL=... nohup ...` en **una sola línea**: así la variable le llega a ese proceso. Con un `export` en otra terminal, o antes de una ejecución vieja, la app muestra "Falta la variable de entorno API_URL" (pasó en este proyecto).
   - `<INVOKE_URL>` sin `/` al final, sin `/preguntas` y sin `< >`.
   - `nohup ... &` deja la app corriendo aunque cierres la terminal. Para detenerla: `pkill -f "streamlit run"`. Si algo falla: `tail -20 streamlit.log`.

5. Abrir en el navegador: `http://<EC2_PUBLIC_DNS>:8501` (es `http`, no `https`).

### 5. Gráficos con matplotlib (en tu computador)

Desde la raíz del proyecto:

```bash
python3 -m venv .venv
.venv/bin/pip install matplotlib requests
.venv/bin/python 08_visualizacion/graficos.py <INVOKE_URL>
```

Genera `08_visualizacion/graficos/q1a_departamentos.png` … `q5_antiguedad_gravedad.png`.

### Acceso a la EC2 desde otra red (por ejemplo, en la sustentación)

La regla SSH solo permite tu IP de casa. Desde otra red, usar **Session Manager** (no necesita el puerto 22 ni la llave): EC2 → seleccionar la instancia → **Conectar** → **Session Manager** → **Conectar**. Para trabajar con los archivos de siempre: `sudo su - ec2-user`. Funciona gracias a `LabInstanceProfile`.

## Evidencias

Archivos en `08_visualizacion/evidencias/`:

- [`01_lambda.png`](evidencias/01_lambda.png): la función `api_resultados` con su código y API Gateway como desencadenador
- [`02_api_gateway.png`](evidencias/02_api_gateway.png): la API `api-siniestros` con las rutas `GET /preguntas` y `GET /resultados/{pregunta}`
- [`03_api_preguntas.png`](evidencias/03_api_preguntas.png): navegador con `<INVOKE_URL>/preguntas`
- [`04_api_resultado_q4.png`](evidencias/04_api_resultado_q4.png): navegador con `<INVOKE_URL>/resultados/q4_proporcion_mortal` (TRACTOCAMION 28.76…)
- `05_streamlit_q1.png` … `09_streamlit_q5.png`: la app en la EC2, una captura por pregunta, con la URL `:8501` y la ruta de la API usada

Gráficos de matplotlib (generados con `graficos.py` contra la API real), en `08_visualizacion/graficos/`:

- [`q1a_departamentos.png`](graficos/q1a_departamentos.png), [`q1b_municipios.png`](graficos/q1b_municipios.png), [`q2_tipos_vehiculo.png`](graficos/q2_tipos_vehiculo.png), [`q3_evolucion_mensual.png`](graficos/q3_evolucion_mensual.png), [`q4_proporcion_mortal.png`](graficos/q4_proporcion_mortal.png), [`q5_antiguedad_gravedad.png`](graficos/q5_antiguedad_gravedad.png)

## Costos

Lambda y API Gateway: prácticamente cero con este uso (se cobran por llamada). La EC2 es la misma del punto 2: detenerla al terminar.
