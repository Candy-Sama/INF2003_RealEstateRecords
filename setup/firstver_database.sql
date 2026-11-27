-- MySQL Workbench Forward Engineering

SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION';

-- -----------------------------------------------------
-- Schema estateRecordsDB
-- -----------------------------------------------------
CREATE SCHEMA IF NOT EXISTS `estateRecordsDB` DEFAULT CHARACTER SET utf8mb3 ;
USE `estateRecordsDB` ;

-- -----------------------------------------------------
-- Table `estateRecordsDB`.`agents`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `estateRecordsDB`.`agents` (
  `agent_id` INT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(45) NOT NULL,
  `email` VARCHAR(45) NOT NULL,
  `phone_number` VARCHAR(45) NOT NULL,
  `password_hash` VARCHAR(255) NOT NULL,
  PRIMARY KEY (`agent_id`),
  UNIQUE INDEX `email_UNIQUE` (`email` ASC) VISIBLE)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb3;


-- -----------------------------------------------------
-- Table `estateRecordsDB`.`place`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `estateRecordsDB`.`place` (
  `block_id` INT NOT NULL AUTO_INCREMENT,
  `block_number` VARCHAR(45) NOT NULL,
  `road_name` VARCHAR(45) NOT NULL,
  `postal` VARCHAR(45) NOT NULL,
  `latitude` DECIMAL(18,15) NOT NULL,
  `longtitude` DECIMAL(18,15) NOT NULL,
  `town` VARCHAR(45) NOT NULL,
  PRIMARY KEY (`block_id`),
  INDEX `ix_place_town_address` (`town`, `road_name`, `block_number`),
  INDEX `ix_place_coords` (`latitude`, `longtitude`),
  CONSTRAINT `chk_place_coordinates`
    CHECK (`latitude` BETWEEN -90 AND 90 AND `longtitude` > -180 AND `longtitude` <= 180))
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb3;


-- -----------------------------------------------------
-- Table `estateRecordsDB`.`flat`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `estateRecordsDB`.`flat` (
  `flat_id` INT NOT NULL AUTO_INCREMENT,
  `flat_type` VARCHAR(45) NOT NULL,
  `flat_model` VARCHAR(45) NOT NULL,
  `storey_range` VARCHAR(45) NOT NULL,
  `floor_area_sqm` DECIMAL(7,2) NOT NULL,
  `block_id` INT NOT NULL,
  `lease_commence_date` INT NOT NULL,
  `remaining_lease_months` INT NOT NULL,
  PRIMARY KEY (`flat_id`),
  INDEX `fk_RESALE_TRANSACTION_BLOCK1_idx` (`block_id` ASC) VISIBLE,
  INDEX `ix_flat_type_block` (`flat_type`, `block_id`),
  CONSTRAINT `chk_flat_area` CHECK (`floor_area_sqm` > 0),
  CONSTRAINT `chk_flat_remaining_lease` CHECK (`remaining_lease_months` >= 0),
  CONSTRAINT `fk_RESALE_TRANSACTION_BLOCK1`
    FOREIGN KEY (`block_id`)
    REFERENCES `estateRecordsDB`.`place` (`block_id`))
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb3;


-- -----------------------------------------------------
-- Table `estateRecordsDB`.`stations`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `estateRecordsDB`.`stations` (
  `station_id` INT NOT NULL AUTO_INCREMENT,
  `station_code` VARCHAR(45) NOT NULL,
  `station_name` VARCHAR(45) NOT NULL,
  `line_name` VARCHAR(45) NOT NULL,
  `line_color` VARCHAR(45) NOT NULL,
  `transport_type` ENUM('MRT', 'LRT') NOT NULL,
  `place_block_id` INT NOT NULL,
  PRIMARY KEY (`station_id`),
  UNIQUE INDEX `station_code_UNIQUE` (`station_code` ASC) VISIBLE,
  INDEX `fk_stations_place1_idx` (`place_block_id` ASC) VISIBLE,
  CONSTRAINT `fk_stations_place1`
    FOREIGN KEY (`place_block_id`)
    REFERENCES `estateRecordsDB`.`place` (`block_id`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb3;


-- -----------------------------------------------------
-- Table `estateRecordsDB`.`nearby`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `estateRecordsDB`.`nearby` (
  `STATIONS_station_id` INT NOT NULL,
  `PLACE_block_id` INT NOT NULL,
  `distance_m` INT NOT NULL,
  PRIMARY KEY (`STATIONS_station_id`, `PLACE_block_id`),
  INDEX `ix_nearby_block_distance` (`PLACE_block_id`, `distance_m`),
  CONSTRAINT `chk_nearby_distance` CHECK (`distance_m` >= 0),
  CONSTRAINT `fk_STATIONS_has_PLACE_PLACE1`
    FOREIGN KEY (`PLACE_block_id`)
    REFERENCES `estateRecordsDB`.`place` (`block_id`),
  CONSTRAINT `fk_STATIONS_has_PLACE_STATIONS1`
    FOREIGN KEY (`STATIONS_station_id`)
    REFERENCES `estateRecordsDB`.`stations` (`station_id`))
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb3;


-- -----------------------------------------------------
-- Table `estateRecordsDB`.`resale_transaction`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `estateRecordsDB`.`resale_transaction` (
  `FLAT_flat_id` INT NOT NULL,
  `AGENTS_agent_id` INT NOT NULL,
  `transaction_date` DATE NOT NULL,
  `resale_price` DECIMAL(12,2) NOT NULL,
  PRIMARY KEY (`FLAT_flat_id`, `AGENTS_agent_id`),
  INDEX `ix_rt_agent_date_flat` (`AGENTS_agent_id`, `transaction_date`, `FLAT_flat_id`),
  INDEX `ix_rt_date` (`transaction_date`),
  INDEX `ix_rt_price` (`resale_price`),
  CONSTRAINT `chk_resale_price` CHECK (`resale_price` > 0),
  CONSTRAINT `fk_RESALE_TRANSACTION_has_AGENTS_AGENTS1`
    FOREIGN KEY (`AGENTS_agent_id`)
    REFERENCES `estateRecordsDB`.`agents` (`agent_id`),
  CONSTRAINT `fk_RESALE_TRANSACTION_has_AGENTS_RESALE_TRANSACTION1`
    FOREIGN KEY (`FLAT_flat_id`)
    REFERENCES `estateRecordsDB`.`flat` (`flat_id`))
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb3;


-- -----------------------------------------------------
-- View `estateRecordsDB`.`v_resale_detail`
-- Joins resale_transaction, flat, and place without exposing agent columns.
-- -----------------------------------------------------
CREATE OR REPLACE VIEW `estateRecordsDB`.`v_resale_detail` AS
SELECT
  rt.`FLAT_flat_id` AS `flat_id`,
  rt.`transaction_date` AS `transaction_date`,
  rt.`resale_price` AS `resale_price`,
  ROUND(rt.`resale_price` / NULLIF(f.`floor_area_sqm`, 0), 2) AS `price_per_sqm`,
  f.`flat_type` AS `flat_type`,
  f.`flat_model` AS `flat_model`,
  f.`storey_range` AS `storey_range`,
  f.`floor_area_sqm` AS `floor_area_sqm`,
  f.`lease_commence_date` AS `lease_commence_date`,
  f.`remaining_lease_months` AS `remaining_lease_months`,
  p.`block_id` AS `block_id`,
  p.`block_number` AS `block_number`,
  p.`road_name` AS `road_name`,
  p.`postal` AS `postal`,
  p.`town` AS `town`,
  p.`latitude` AS `latitude`,
  p.`longtitude` AS `longtitude`
FROM `estateRecordsDB`.`resale_transaction` AS rt
JOIN `estateRecordsDB`.`flat` AS f
  ON f.`flat_id` = rt.`FLAT_flat_id`
JOIN `estateRecordsDB`.`place` AS p
  ON p.`block_id` = f.`block_id`;

SET SQL_MODE=@OLD_SQL_MODE;
