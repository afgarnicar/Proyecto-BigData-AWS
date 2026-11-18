-- Pregunta 5: ¿qué relación descriptiva existe entre la antigüedad del vehículo y la
-- gravedad del siniestro?
-- Se excluyen las edades NULL y las marcadas como fuera de rango (> 100) en el punto 4.
SELECT
  rango_edad,
  COUNT(*) AS vehiculos,
  SUM(es_mortal) AS con_muertos,
  ROUND(100.0 * SUM(es_mortal) / COUNT(*), 2) AS porcentaje_con_muertos
FROM (
  SELECT
    CASE
      WHEN edad_vehiculo <= 5  THEN '01) 0-5 anios'
      WHEN edad_vehiculo <= 10 THEN '02) 6-10 anios'
      WHEN edad_vehiculo <= 15 THEN '03) 11-15 anios'
      WHEN edad_vehiculo <= 20 THEN '04) 16-20 anios'
      WHEN edad_vehiculo <= 30 THEN '05) 21-30 anios'
      ELSE '06) mas de 30 anios'
    END AS rango_edad,
    CASE WHEN gravedad_accidente = 'CON MUERTOS' THEN 1 ELSE 0 END AS es_mortal
  FROM siniestros.vehiculos
  WHERE edad_vehiculo IS NOT NULL AND edad_fuera_rango = false
) t
GROUP BY rango_edad
ORDER BY rango_edad;
