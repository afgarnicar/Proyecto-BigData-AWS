"""
Punto 8 - aplicación Streamlit que muestra los resultados de las 5 preguntas. Todos los
datos llegan por la API (API Gateway + Lambda): la aplicación no lee S3 directamente.

Uso (en la EC2, en una sola línea; ver 08_visualizacion/README.md):
    API_URL=<INVOKE_URL> streamlit run app.py --server.port 8501 --server.address 0.0.0.0
"""

import os

import pandas as pd
import requests
import streamlit as st

API_URL = os.environ.get("API_URL", "").rstrip("/")

st.set_page_config(page_title="Siniestros viales en Colombia", layout="wide")


@st.cache_data(ttl=600)  # guarda cada respuesta 10 minutos para no llamar a la API en cada clic
def obtener(ruta):
    respuesta = requests.get(f"{API_URL}{ruta}", timeout=20)
    respuesta.raise_for_status()
    return respuesta.json()


def tabla(pregunta):
    datos = obtener(f"/resultados/{pregunta}")
    return datos, pd.DataFrame(datos["filas"], columns=datos["columnas"])


st.title("Vehículos involucrados en siniestros viales en Colombia (2022–2026)")
st.caption(
    "Fuente: Datos Abiertos Colombia / RUNT (dataset 6jmc-vaxk). "
    "Unidad: **vehículos involucrados**, no accidentes únicos. "
    "Datos servidos por API Gateway + Lambda desde la zona refined del data lake en S3."
)

if not API_URL:
    st.error("Falta la variable de entorno API_URL con la dirección de la API Gateway.")
    st.stop()

try:
    preguntas = obtener("/preguntas")["preguntas"]
except requests.RequestException as error:
    st.error(f"No se pudo consultar la API ({API_URL}): {error}")
    st.stop()

opciones = {p["descripcion"]: p["id"] for p in preguntas}
eleccion = st.sidebar.radio("Pregunta de negocio", list(opciones))
pregunta = opciones[eleccion]
st.sidebar.markdown(f"API: `{API_URL}/resultados/{pregunta}`")

datos, df = tabla(pregunta)
st.header(datos["descripcion"])

if pregunta == "q1a_departamentos":
    top = st.slider("Cantidad de departamentos", 5, len(df), 10)
    vista = df.head(top)
    st.bar_chart(vista, x="departamento_accidente", y="vehiculos")

elif pregunta == "q1b_municipios":
    vista = df.assign(municipio=df["municipio_accidente"] + " (" + df["departamento_accidente"] + ")")
    st.bar_chart(vista, x="municipio", y="vehiculos")

elif pregunta == "q2_tipos_vehiculo":
    top = st.slider("Cantidad de tipos de vehículo", 5, len(df), 10)
    vista = df.head(top)
    st.bar_chart(vista, x="tipo_vehiculo", y="vehiculos")

elif pregunta == "q3_evolucion_mensual":
    anios = sorted(df["anio"].unique())
    desde, hasta = st.select_slider("Años", options=anios, value=(anios[0], anios[-1]))
    vista = df[(df["anio"] >= desde) & (df["anio"] <= hasta)].copy()
    vista["periodo"] = vista["anio"].astype(str) + "-" + vista["mes"].astype(str).str.zfill(2)
    st.line_chart(vista, x="periodo", y="vehiculos")
    st.info(
        "07/2024 (28.854) es un valor atípico alto frente a los meses vecinos. "
        "08/2026 y 09/2026 parecen meses incompletos en el corte consultado."
    )

elif pregunta == "q4_proporcion_mortal":
    vista = df
    st.bar_chart(vista, x="tipo_vehiculo", y="porcentaje_con_muertos")
    st.info(
        "Proporción de registros asociados a siniestros CON MUERTOS dentro de cada tipo. "
        "No es una tasa de mortalidad de ocupantes. Solo tipos con al menos 500 registros."
    )

elif pregunta == "q5_antiguedad_gravedad":
    vista = df
    st.bar_chart(vista, x="rango_edad", y="porcentaje_con_muertos")
    st.info(
        "Relación descriptiva, no causal. Se excluyen 20 edades vacías y 65 edades mayores a 100 años."
    )

st.subheader("Datos")
st.dataframe(vista, hide_index=True)
