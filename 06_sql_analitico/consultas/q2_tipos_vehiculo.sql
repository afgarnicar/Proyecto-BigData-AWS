-- Pregunta 2: ¿cuáles son los tipos de vehículo más frecuentemente involucrados?
SELECT
  tipo_vehiculo,
  COUNT(*) AS vehiculos,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS porcentaje
FROM siniestros.vehiculos
GROUP BY tipo_vehiculo
ORDER BY vehiculos DESC;
