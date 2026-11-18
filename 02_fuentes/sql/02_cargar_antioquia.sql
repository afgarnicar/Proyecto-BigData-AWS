-- Punto 2 - carga el CSV de Antioquia en la tabla. Se puede repetir: TRUNCATE la vacía antes.
-- Ejecutar desde la EC2:  mysql $SSL --local-infile=1 -h $RDS -u admin -p < 02_cargar_antioquia.sql
--
-- Las columnas numéricas pasan por una @variable y NULLIF: sin esto, MariaDB guardaría
-- un campo vacío como 0 y las edades faltantes quedarían como "0 años".

USE siniestros_viales;

TRUNCATE TABLE vehiculos_involucrados;

LOAD DATA LOCAL INFILE 'fuente_rds_antioquia.csv'
INTO TABLE vehiculos_involucrados
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' ESCAPED BY ''
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(socrata_row_id, marca_vehiculo, @modelo_vehiculo, tipo_vehiculo, @edad_vehiculo,
 fecha_accidente, gravedad_accidente, departamento_accidente, municipio_accidente,
 autoridad_de_transito)
SET
  modelo_vehiculo = NULLIF(@modelo_vehiculo, ''),
  edad_vehiculo   = NULLIF(@edad_vehiculo, '');

-- Cualquier advertencia aquí (texto truncado, número inválido) se debe revisar antes de continuar.
SHOW WARNINGS LIMIT 20;
