-- Pregunta 3: ¿cómo ha evolucionado mensualmente la cantidad de vehículos involucrados?
SELECT
  anio,
  mes,
  COUNT(*) AS vehiculos
FROM siniestros.vehiculos
GROUP BY anio, mes
ORDER BY anio, mes;
