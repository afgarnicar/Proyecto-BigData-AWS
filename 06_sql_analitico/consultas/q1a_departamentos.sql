-- Pregunta 1a: ¿qué departamentos registran mayor cantidad de vehículos involucrados?
SELECT
  departamento_accidente,
  COUNT(*) AS vehiculos,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS porcentaje
FROM siniestros.vehiculos
GROUP BY departamento_accidente
ORDER BY vehiculos DESC;
