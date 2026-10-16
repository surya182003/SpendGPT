CREATE DATABASE IF NOT EXISTS seed_data;
USE seed_data;

-- 1. Users Table
CREATE TABLE users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    base_currency VARCHAR(3) DEFAULT 'EUR',
    monthly_income DECIMAL(10, 2) DEFAULT 0.00,
    savings_goal DECIMAL(10, 2) DEFAULT 0.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


INSERT INTO users (
    first_name, 
    last_name, 
    email, 
    password_hash
) VALUES (
    'Kesav', 
    'Pillai', 
    'kesav.pillai@gmail.com', 
    '$2b$12$e80yqVzH...sampleHash...'
);


select * from users;

UPDATE users 
SET password_hash = '$2a$12$uWS8Xz3td7yUU8VXwYdxW.3FeE2kPIcWiUR01SwncaCy1IwZFk11K' 
WHERE email = 'kesav.pillai@gmail.com';