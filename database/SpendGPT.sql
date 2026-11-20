-- SpendGPT schema for TiDB Cloud (MySQL-compatible)
-- the password_hash field is for storing hashed passwords (e.g., bcrypt)
-- the host for the database connection is gateway01.eu-central-1.prod.aws.tidbcloud.com
-- the port is 4000
-- password is the one ive generated and stored in the .env file, and the username is the one ive generated and stored in the .env file
-- the .env file should be in the root of the project and should contain the following variables:
-- TIDB_HOST=gateway01.eu-central-1.prod.aws.tidbcloud.com
-- TIDB_PORT=4000
-- TIDB_USER=<your_username>
-- TIDB_PASSWORD=<your_password>
--TIDB_DATABASE=student_spend_db
-- the details for this is shared in whatsapp, and the password is stored in the .env file, which is not shared publicly for security reasons.
-- do not share the .env file or the password publicly, as it contains sensitive information.
-- do not commit the .env file to version control, as it contains sensitive information.
-- please add the .env file to your .gitignore file to prevent it from being committed to version control.
-- if youve commited the .env file to version control, please remove it and change the password immediately, as it has been compromised.

CREATE DATABASE IF NOT EXISTS student_spend_db;
USE student_spend_db;

-- 1. Users
CREATE TABLE IF NOT EXISTS users (
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

-- 2. Categories
CREATE TABLE IF NOT EXISTS categories (
    category_id INT AUTO_INCREMENT PRIMARY KEY,
    category_name VARCHAR(50) UNIQUE NOT NULL,
    spend_type VARCHAR(20) NOT NULL   -- 'Essential' or 'Discretionary'
);

-- 3. Transactions (one row per receipt)
-- receipt_hash = hash of the receipt image/parsed text, stops OCR re-scans double-counting
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    category_id INT,
    amount DECIMAL(10, 2) NOT NULL,
    merchant_name VARCHAR(100) NOT NULL,
    transaction_date DATE NOT NULL,
    is_recurring BOOLEAN DEFAULT FALSE,
    receipt_hash CHAR(64),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES categories(category_id) ON DELETE SET NULL,
    UNIQUE KEY uq_user_receipt (user_id, receipt_hash),
    INDEX idx_user_date (user_id, transaction_date),
    INDEX idx_category (category_id)
);

-- 4. Receipt line items (per-product data from the OCR pipeline)
-- normalized_name = cleaned product name used to match against reference_prices
CREATE TABLE IF NOT EXISTS receipt_items (
    item_id INT AUTO_INCREMENT PRIMARY KEY,
    transaction_id INT NOT NULL,
    item_name VARCHAR(150) NOT NULL,
    normalized_name VARCHAR(150),
    quantity DECIMAL(8, 2) DEFAULT 1,
    unit_price DECIMAL(10, 2) NOT NULL,
    FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id) ON DELETE CASCADE,
    INDEX idx_transaction (transaction_id),
    INDEX idx_normalized (normalized_name)
);

-- 5. Reference prices (Open Basket data is loaded here)
CREATE TABLE IF NOT EXISTS reference_prices (
    ref_id INT AUTO_INCREMENT PRIMARY KEY,
    product_name VARCHAR(150) NOT NULL,
    normalized_name VARCHAR(150),
    retailer VARCHAR(80),
    unit_size VARCHAR(50),             -- e.g. '1L', '500g'
    price DECIMAL(10, 2) NOT NULL,
    source VARCHAR(50) DEFAULT 'open_basket',
    observed_on DATE NOT NULL,
    INDEX idx_ref_normalized (normalized_name),
    INDEX idx_ref_observed (observed_on)
);

-- 6. Budgets
CREATE TABLE IF NOT EXISTS budgets (
    budget_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    category_id INT,
    amount_limit DECIMAL(10, 2) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES categories(category_id) ON DELETE CASCADE,
    UNIQUE (user_id, category_id, start_date)
);

-- 7. Alerts
CREATE TABLE IF NOT EXISTS alerts (
    alert_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    alert_type VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    related_transaction_id INT,
    related_budget_id INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (related_transaction_id) REFERENCES transactions(transaction_id) ON DELETE SET NULL,
    FOREIGN KEY (related_budget_id) REFERENCES budgets(budget_id) ON DELETE SET NULL
);

-- 8. Accounts
CREATE TABLE IF NOT EXISTS accounts (
    account_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    account_name VARCHAR(100) NOT NULL,
    account_type VARCHAR(50) NOT NULL,  -- e.g. 'Current', 'Savings'
    current_balance DECIMAL(10, 2) DEFAULT 0.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- 9. Predictions
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    category_id INT,                    -- NULL = forecast of total overall spend
    target_month DATE NOT NULL,         -- first day of the forecast month, e.g. '2026-12-01'
    predicted_amount DECIMAL(10, 2) NOT NULL,
    model_version VARCHAR(50),         \-- e.g. 'v1.0', 'v2.1'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES categories(category_id) ON DELETE SET NULL,
    INDEX idx_pred_user_month (user_id, target_month)
);

-- Seed categories
INSERT IGNORE INTO categories (category_name, spend_type) VALUES
    ('Groceries',     'Essential'),
    ('Rent',          'Essential'),
    ('Utilities',     'Essential'),
    ('Transport',     'Essential'),
    ('Health',        'Essential'),
    ('Eating Out',    'Discretionary'),
    ('Shopping',      'Discretionary'),
    ('Entertainment', 'Discretionary'),
    ('Subscriptions', 'Discretionary'),
    ('Other',         'Discretionary');