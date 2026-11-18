-- Pregunta 1b: ¿qué municipios registran mayor cantidad de vehículos involucrados? (top 15)
SELECT
  departamento_accidente,
  municipio_accidente,
  COUNT(*) AS vehiculos
FROM siniestros.vehiculos
GROUP BY departamento_accidente, municipio_accidente
ORDER BY vehiculos DESC
LIMIT 15;
