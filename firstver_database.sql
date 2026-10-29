-- MySQL Workbench Forward Engineering

SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0;
SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0;
SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION';

-- -----------------------------------------------------
-- Schema mydb
-- -----------------------------------------------------
DROP SCHEMA IF EXISTS `mydb` ;

-- -----------------------------------------------------
-- Schema mydb
-- -----------------------------------------------------
CREATE SCHEMA IF NOT EXISTS `mydb` DEFAULT CHARACTER SET utf8mb3 ;
USE `mydb` ;

-- -----------------------------------------------------
-- Table `mydb`.`nosql`
-- -----------------------------------------------------
DROP TABLE IF EXISTS `mydb`.`nosql` ;

CREATE TABLE IF NOT EXISTS `mydb`.`nosql` (
  `idNoSQL` INT NOT NULL,
  `NoSQLData` JSON NULL DEFAULT NULL,
  PRIMARY KEY (`idNoSQL`))
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb3;


-- -----------------------------------------------------
-- Table `mydb`.`agents`
-- -----------------------------------------------------
DROP TABLE IF EXISTS `mydb`.`agents` ;

CREATE TABLE IF NOT EXISTS `mydb`.`agents` (
  `agent_id` INT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(45) NOT NULL,
  `email` VARCHAR(45) NOT NULL,
  `phone_number` VARCHAR(45) NOT NULL,
  `password_hash` VARCHAR(255) NOT NULL,
  `NoSQL_idNoSQL` INT NOT NULL,
  PRIMARY KEY (`agent_id`),
  UNIQUE INDEX `agent_id_UNIQUE` (`agent_id` ASC) VISIBLE,
  INDEX `fk_AGENTS_NoSQL1_idx` (`NoSQL_idNoSQL` ASC) VISIBLE,
  CONSTRAINT `fk_AGENTS_NoSQL1`
    FOREIGN KEY (`NoSQL_idNoSQL`)
    REFERENCES `mydb`.`nosql` (`idNoSQL`))
ENGINE = InnoDB
AUTO_INCREMENT = 2
DEFAULT CHARACTER SET = utf8mb3;


-- -----------------------------------------------------
-- Table `mydb`.`place`
-- -----------------------------------------------------
DROP TABLE IF EXISTS `mydb`.`place` ;

CREATE TABLE IF NOT EXISTS `mydb`.`place` (
  `block_id` INT NOT NULL AUTO_INCREMENT,
  `block_number` VARCHAR(45) NOT NULL,
  `road_name` VARCHAR(45) NOT NULL,
  `postal` VARCHAR(45) NOT NULL,
  `latitude` FLOAT NOT NULL,
  `longtitude` FLOAT NOT NULL,
  `town` VARCHAR(45) NOT NULL,
  PRIMARY KEY (`block_id`),
  UNIQUE INDEX `block_id_UNIQUE` (`block_id` ASC) VISIBLE)
ENGINE = InnoDB
AUTO_INCREMENT = 9762
DEFAULT CHARACTER SET = utf8mb3;


-- -----------------------------------------------------
-- Table `mydb`.`flat`
-- -----------------------------------------------------
DROP TABLE IF EXISTS `mydb`.`flat` ;

CREATE TABLE IF NOT EXISTS `mydb`.`flat` (
  `flat_id` INT NOT NULL AUTO_INCREMENT,
  `flat_type` VARCHAR(45) NOT NULL,
  `flat_model` VARCHAR(45) NOT NULL,
  `storey_range` VARCHAR(45) NOT NULL,
  `floor_area_sqm` INT NOT NULL,
  `block_id` INT NOT NULL,
  `lease_commence_date` INT NOT NULL,
  `remaining_lease_months` INT NOT NULL,
  PRIMARY KEY (`flat_id`),
  UNIQUE INDEX `transaction_id_UNIQUE` (`flat_id` ASC) VISIBLE,
  INDEX `fk_RESALE_TRANSACTION_BLOCK1_idx` (`block_id` ASC) VISIBLE,
  CONSTRAINT `fk_RESALE_TRANSACTION_BLOCK1`
    FOREIGN KEY (`block_id`)
    REFERENCES `mydb`.`place` (`block_id`))
ENGINE = InnoDB
AUTO_INCREMENT = 242635
DEFAULT CHARACTER SET = utf8mb3;


-- -----------------------------------------------------
-- Table `mydb`.`stations`
-- -----------------------------------------------------
DROP TABLE IF EXISTS `mydb`.`stations` ;

CREATE TABLE IF NOT EXISTS `mydb`.`stations` (
  `station_id` INT NOT NULL AUTO_INCREMENT,
  `station_code` VARCHAR(45) NOT NULL,
  `station_name` VARCHAR(45) NOT NULL,
  `line_name` VARCHAR(45) NOT NULL,
  `line_color` VARCHAR(45) NOT NULL,
  `transport_type` ENUM('MRT', 'LRT') NOT NULL,
  `place_block_id` INT NOT NULL,
  PRIMARY KEY (`station_id`),
  UNIQUE INDEX `station_id_UNIQUE` (`station_id` ASC) VISIBLE,
  UNIQUE INDEX `station_code_UNIQUE` (`station_code` ASC) VISIBLE,
  INDEX `fk_stations_place1_idx` (`place_block_id` ASC) VISIBLE,
  CONSTRAINT `fk_stations_place1`
    FOREIGN KEY (`place_block_id`)
    REFERENCES `mydb`.`place` (`block_id`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb3;


-- -----------------------------------------------------
-- Table `mydb`.`nearby`
-- -----------------------------------------------------
DROP TABLE IF EXISTS `mydb`.`nearby` ;

CREATE TABLE IF NOT EXISTS `mydb`.`nearby` (
  `STATIONS_station_id` INT NOT NULL,
  `PLACE_block_id` INT NOT NULL,
  PRIMARY KEY (`STATIONS_station_id`, `PLACE_block_id`),
  INDEX `fk_STATIONS_has_PLACE_PLACE1_idx` (`PLACE_block_id` ASC) VISIBLE,
  INDEX `fk_STATIONS_has_PLACE_STATIONS1_idx` (`STATIONS_station_id` ASC) VISIBLE,
  CONSTRAINT `fk_STATIONS_has_PLACE_PLACE1`
    FOREIGN KEY (`PLACE_block_id`)
    REFERENCES `mydb`.`place` (`block_id`),
  CONSTRAINT `fk_STATIONS_has_PLACE_STATIONS1`
    FOREIGN KEY (`STATIONS_station_id`)
    REFERENCES `mydb`.`stations` (`station_id`))
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb3;


-- -----------------------------------------------------
-- Table `mydb`.`resale_transaction`
-- -----------------------------------------------------
DROP TABLE IF EXISTS `mydb`.`resale_transaction` ;

CREATE TABLE IF NOT EXISTS `mydb`.`resale_transaction` (
  `FLAT_flat_id` INT NOT NULL,
  `AGENTS_agent_id` INT NOT NULL,
  `transacton_date` DATE NOT NULL,
  `resale_price` FLOAT NOT NULL,
  PRIMARY KEY (`FLAT_flat_id`, `AGENTS_agent_id`),
  INDEX `fk_RESALE_TRANSACTION_has_AGENTS_AGENTS1_idx` (`AGENTS_agent_id` ASC) VISIBLE,
  INDEX `fk_RESALE_TRANSACTION_has_AGENTS_RESALE_TRANSACTION1_idx` (`FLAT_flat_id` ASC) VISIBLE,
  CONSTRAINT `fk_RESALE_TRANSACTION_has_AGENTS_AGENTS1`
    FOREIGN KEY (`AGENTS_agent_id`)
    REFERENCES `mydb`.`agents` (`agent_id`),
  CONSTRAINT `fk_RESALE_TRANSACTION_has_AGENTS_RESALE_TRANSACTION1`
    FOREIGN KEY (`FLAT_flat_id`)
    REFERENCES `mydb`.`flat` (`flat_id`))
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb3;


SET SQL_MODE=@OLD_SQL_MODE;
SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS;
SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS;
