CREATE DATABASE IF NOT EXISTS parking_db DEFAULT CHARACTER SET utf8mb4;
USE parking_db;

-- 用户表
DROP TABLE IF EXISTS users;
CREATE TABLE users(
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(50) NOT NULL,
    role VARCHAR(20) NOT NULL -- user / admin
);

-- 车位表
DROP TABLE IF EXISTS parking_spaces;
CREATE TABLE parking_spaces(
    id INT PRIMARY KEY AUTO_INCREMENT,
    location VARCHAR(50) NOT NULL,
    status TINYINT NOT NULL -- 0空闲，1占用，2已预约
);

-- 预约表
DROP TABLE IF EXISTS reservations;
CREATE TABLE reservations(
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    space_id INT NOT NULL,
    start_time DATETIME,
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(space_id) REFERENCES parking_spaces(id)
);

-- 插入测试账号和车位（答辩演示数据）
INSERT INTO users(username,password,role) VALUES
('admin','admin123','admin'),
('testuser','test123','user');

INSERT INTO parking_spaces(location,status) VALUES
('A01',0),('A02',0),('A03',0),('B01',0),('B02',0);
