-- Punto 2 - verifica que la tabla quedó igual que el CSV (valores esperados del corte 2026-11-15).
-- Ejecutar desde la EC2:  mysql $SSL -h $RDS -u admin -p -t < 03_verificar_carga.sql | tee rds_verificacion.txt

USE siniestros_viales;

-- 1) Total de filas: esperado 175618.
SELECT COUNT(*) AS total_filas FROM vehiculos_involucrados;

-- 2) Departamentos: esperada una sola fila, ANTIOQUIA | 175618.
SELECT departamento_accidente, COUNT(*) AS filas
FROM vehiculos_involucrados
GROUP BY departamento_accidente;

-- 3) Vacíos: esperado edad_null = 5, edad_cero = 251, modelo_null = 0.
--    Si edad_null = 0 y edad_cero = 256, el NULLIF falló: los vacíos se volvieron 0.
SELECT
  SUM(edad_vehiculo IS NULL)   AS edad_null,
  SUM(edad_vehiculo = 0)       AS edad_cero,
  SUM(modelo_vehiculo IS NULL) AS modelo_null
FROM vehiculos_involucrados;

-- 4) Vistazo a 5 filas: revisar que tildes, números y columnas se vean bien.
SELECT * FROM vehiculos_involucrados LIMIT 5;
