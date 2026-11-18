-- Pregunta 4: ¿qué tipos de vehículo presentan mayor proporción de registros asociados
-- a siniestros mortales?
-- Solo tipos con al menos 500 registros: con pocos, la proporción engaña (1 buldozer mortal = 100 %).
SELECT
  tipo_vehiculo,
  COUNT(*) AS vehiculos,
  SUM(CASE WHEN gravedad_accidente = 'CON MUERTOS' THEN 1 ELSE 0 END) AS con_muertos,
  ROUND(100.0 * SUM(CASE WHEN gravedad_accidente = 'CON MUERTOS' THEN 1 ELSE 0 END) / COUNT(*), 2) AS porcentaje_con_muertos
FROM siniestros.vehiculos
GROUP BY tipo_vehiculo
HAVING COUNT(*) >= 500
ORDER BY porcentaje_con_muertos DESC;
