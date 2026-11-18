"""
Punto 8 - genera con matplotlib un gráfico PNG por pregunta en 08_visualizacion/graficos/,
pidiendo los datos a la misma API (API Gateway + Lambda) que usa la aplicación Streamlit.

Uso (en tu computador; ver 08_visualizacion/README.md):
    pip install matplotlib requests
    python3 08_visualizacion/graficos.py <INVOKE_URL>
"""

import os
import sys

import matplotlib

matplotlib.use("Agg")  # genera imágenes sin abrir ventanas
import matplotlib.pyplot as plt
import requests

CARPETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "graficos")
FUENTE = "Fuente: Datos Abiertos Colombia / RUNT (6jmc-vaxk). Unidad: vehículos involucrados."


def obtener(api_url, pregunta):
    respuesta = requests.get(f"{api_url}/resultados/{pregunta}", timeout=20)
    respuesta.raise_for_status()
    return respuesta.json()["filas"]


def guardar(figura, nombre):
    figura.text(0.01, 0.01, FUENTE, fontsize=8, color="gray")
    figura.tight_layout(rect=(0, 0.03, 1, 1))
    ruta = os.path.join(CARPETA, nombre)
    figura.savefig(ruta, dpi=150)
    plt.close(figura)
    print(f"  {ruta}")


def barras_horizontales(filas, etiqueta, valor, titulo, eje_x, nombre, formato="{:,.0f}"):
    filas = list(reversed(filas))  # el mayor queda arriba
    figura, eje = plt.subplots(figsize=(10, 6))
    barras = eje.barh([f[etiqueta] for f in filas], [f[valor] for f in filas], color="#2a6f97")
    eje.bar_label(barras, labels=[formato.format(f[valor]).replace(",", ".") for f in filas], padding=3, fontsize=8)
    eje.set_title(titulo)
    eje.set_xlabel(eje_x)
    eje.margins(x=0.12)
    guardar(figura, nombre)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    api_url = sys.argv[1].rstrip("/")
    os.makedirs(CARPETA, exist_ok=True)
    print("Gráficos generados:")

    departamentos = obtener(api_url, "q1a_departamentos")[:10]
    barras_horizontales(departamentos, "departamento_accidente", "vehiculos",
                        "Pregunta 1: top 10 departamentos", "Vehículos involucrados", "q1a_departamentos.png")

    municipios = obtener(api_url, "q1b_municipios")
    for fila in municipios:
        fila["municipio"] = f"{fila['municipio_accidente']} ({fila['departamento_accidente']})"
    barras_horizontales(municipios, "municipio", "vehiculos",
                        "Pregunta 1: top 15 municipios", "Vehículos involucrados", "q1b_municipios.png")

    tipos = obtener(api_url, "q2_tipos_vehiculo")[:10]
    barras_horizontales(tipos, "tipo_vehiculo", "vehiculos",
                        "Pregunta 2: top 10 tipos de vehículo", "Vehículos involucrados", "q2_tipos_vehiculo.png")

    meses = obtener(api_url, "q3_evolucion_mensual")
    figura, eje = plt.subplots(figsize=(12, 5))
    etiquetas = [f"{f['anio']}-{f['mes']:02d}" for f in meses]
    eje.plot(etiquetas, [f["vehiculos"] for f in meses], marker="o", markersize=3, color="#2a6f97")
    eje.set_xticks(range(0, len(etiquetas), 3))
    eje.set_xticklabels(etiquetas[::3], rotation=45, ha="right", fontsize=8)
    eje.set_title("Pregunta 3: evolución mensual (07/2024 atípico; 08-09/2026 incompletos)")
    eje.set_ylabel("Vehículos involucrados")
    eje.grid(alpha=0.3)
    guardar(figura, "q3_evolucion_mensual.png")

    mortal = obtener(api_url, "q4_proporcion_mortal")
    barras_horizontales(mortal, "tipo_vehiculo", "porcentaje_con_muertos",
                        "Pregunta 4: % de registros CON MUERTOS por tipo (≥ 500 registros)",
                        "% de registros asociados a siniestros mortales", "q4_proporcion_mortal.png",
                        formato="{:.2f} %")

    edades = obtener(api_url, "q5_antiguedad_gravedad")
    figura, eje = plt.subplots(figsize=(10, 5))
    barras = eje.bar([f["rango_edad"][4:] for f in edades], [f["porcentaje_con_muertos"] for f in edades],
                     color="#a4161a")
    eje.bar_label(barras, labels=[f"{f['porcentaje_con_muertos']:.2f} %" for f in edades], padding=3, fontsize=9)
    eje.set_title("Pregunta 5: % de registros CON MUERTOS por antigüedad del vehículo")
    eje.set_ylabel("% de registros asociados a siniestros mortales")
    eje.margins(y=0.15)
    guardar(figura, "q5_antiguedad_gravedad.png")


if __name__ == "__main__":
    main()
