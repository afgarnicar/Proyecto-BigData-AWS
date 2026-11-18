# Punto 1 — Caso de estudio

## Caso

**Análisis de vehículos involucrados en siniestros viales en Colombia (2022–2026).**
Se describen patrones geográficos, temporales, por tipo y antigüedad de vehículo, y por gravedad, como insumo descriptivo para seguridad vial.

## Dataset

| Campo | Valor |
|---|---|
| Nombre | Vehículos involucrados en un accidente de tránsito — Ley 2251 de 2022 |
| Publicador | Datos Abiertos Colombia / RUNT, Ministerio de Transporte |
| Página | https://www.datos.gov.co/Transporte/VEHICULOS-INVOLUCRADOS-EN-UN-ACCIDENTE-DE-TRANSITO/6jmc-vaxk |
| API | https://www.datos.gov.co/resource/6jmc-vaxk.json (también `.csv`) |
| Periodo | 2022 a 2026 |

Columnas (9): `marca_vehiculo`, `modelo_vehiculo`, `tipo_vehiculo`, `edad_vehiculo`, `fecha_accidente` (texto `MM/YYYY`), `gravedad_accidente`, `departamento_accidente`, `municipio_accidente`, `autoridad_de_transito`.

## Cinco preguntas de negocio

1. ¿Qué departamentos y municipios registran mayor cantidad de vehículos involucrados en siniestros viales?
2. ¿Cuáles son los tipos de vehículos más frecuentemente involucrados?
3. ¿Cómo ha evolucionado mensualmente la cantidad de vehículos involucrados?
4. ¿Qué tipos de vehículos presentan mayor proporción de registros asociados a siniestros mortales? (filas `CON MUERTOS` / filas del tipo; no es una tasa de mortalidad de ocupantes)
5. ¿Qué relación descriptiva existe entre la antigüedad del vehículo y la gravedad del siniestro?

## Reparto entre las tres fuentes exigidas

Conteos según la consulta a la API del 2026-11-14 (el origen se puede actualizar, así que corresponden a ese corte):

| Fuente | Criterio (SoQL) | Filas |
|---|---|---:|
| RDS MariaDB | `departamento_accidente = 'ANTIOQUIA'` | 175.618 |
| Archivo CSV en EC2 | `departamento_accidente = 'BOGOTA D.C.'` | 62.990 |
| URL pública (API Socrata) | `departamento_accidente NOT IN ('ANTIOQUIA','BOGOTA D.C.') OR departamento_accidente IS NULL` | 211.727 |
| **Total del dataset** | | **450.335** |

## Evidencias

Capturas de pantalla que respaldan los números de este README:

- [`evidencias/01_pagina_dataset.png`](evidencias/01_pagina_dataset.png): página del dataset en datos.gov.co
- [`evidencias/02_colab_total.png`](evidencias/02_colab_total.png): consulta en Colab con el total de filas (450.335)
- [`evidencias/03_colab_por_fuente.png`](evidencias/03_colab_por_fuente.png): consulta en Colab con los conteos de Antioquia y Bogotá D.C.
