-- Punto 2 - crea la base siniestros_viales y la tabla de vehículos de Antioquia en RDS.
-- Ejecutar desde la EC2:  mysql $SSL -h $RDS -u admin -p < 01_crear_tabla.sql
-- Una fila = un vehículo involucrado (no un accidente).

CREATE DATABASE IF NOT EXISTS siniestros_viales
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE siniestros_viales;

CREATE TABLE IF NOT EXISTS vehiculos_involucrados (
  socrata_row_id          VARCHAR(32)  NOT NULL,
  marca_vehiculo          VARCHAR(100) NULL,
  modelo_vehiculo         SMALLINT     NULL,  -- año del modelo del vehículo (ej. 2018)
  tipo_vehiculo           VARCHAR(60)  NULL,
  edad_vehiculo           SMALLINT     NULL,  -- puede venir vacía (NULL); se conserva así, sin inventar un valor
  fecha_accidente         CHAR(7)      NULL,  -- texto 'MM/YYYY', se separa en año y mes en TRUSTED
  gravedad_accidente      VARCHAR(30)  NULL,
  departamento_accidente  VARCHAR(80)  NULL,
  municipio_accidente     VARCHAR(100) NULL,
  autoridad_de_transito   VARCHAR(150) NULL,
  PRIMARY KEY (socrata_row_id)
);
