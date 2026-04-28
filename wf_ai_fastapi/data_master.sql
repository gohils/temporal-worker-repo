-- =========================================
-- 1. ENTITY REGISTRY (FIXED CONTRACT)
-- =========================================

DROP TABLE IF EXISTS entity_registry CASCADE;

CREATE TABLE entity_registry (
    entity_name VARCHAR(100) PRIMARY KEY,
    table_name  VARCHAR(100) NOT NULL,
    pk          VARCHAR(50) NOT NULL,
    config      JSONB,
    updated_at  TIMESTAMP DEFAULT now()
);

INSERT INTO entity_registry (entity_name, table_name, pk, config)
VALUES
('vendor',   'vendor_master',   'vendor_id',   '{}'),
('customer', 'customer_master', 'customer_id', '{}'),
('product',  'product_master',  'product_id',  '{}');


-- =========================================
-- 2. VENDOR MASTER
-- =========================================

DROP TABLE IF EXISTS vendor_master CASCADE;

CREATE TABLE vendor_master (
    vendor_id     VARCHAR(50) PRIMARY KEY,
    vendor_name   VARCHAR(255) NOT NULL,
    tax_id        VARCHAR(50),
    address       VARCHAR(500),
    payment_terms VARCHAR(50),
    currency      VARCHAR(10),
    status        VARCHAR(20)
);

INSERT INTO vendor_master (
    vendor_id,
    vendor_name,
    tax_id,
    address,
    payment_terms,
    currency,
    status
)
VALUES (
    'VEND-0001',
    'Fortune Global Ltd',
    '12 034 112 123',
    '15 Main Street, Melbourne, VIC 3029',
    'Net 30',
    'AUD',
    'Active'
);


-- =========================================
-- 3. CUSTOMER MASTER
-- =========================================

DROP TABLE IF EXISTS customer_master CASCADE;

CREATE TABLE customer_master (
    customer_id   VARCHAR(50) PRIMARY KEY,
    customer_name VARCHAR(255) NOT NULL,
    address       VARCHAR(500),
    email         VARCHAR(255),
    phone         VARCHAR(50),
    city          VARCHAR(100),
    state         VARCHAR(50),
    postal_code   VARCHAR(20),
    country       VARCHAR(50),
    status        VARCHAR(20)
);

INSERT INTO customer_master (
    customer_id,
    customer_name,
    address,
    email,
    phone,
    city,
    state,
    postal_code,
    country,
    status
)
VALUES
(
    'CUST-0001',
    'John Doe',
    '22 High Street, Melbourne, VIC 3000',
    NULL,
    NULL,
    'Melbourne',
    'VIC',
    '3000',
    'Australia',
    'Active'
),
(
    'CUST-0002',
    'David Smith',
    '55 Park Street, Sydney, NSW 2000',
    NULL,
    NULL,
    'Sydney',
    'NSW',
    '2000',
    'Australia',
    'Active'
);


-- =========================================
-- 4. PRODUCT MASTER (MATERIAL)
-- =========================================

DROP TABLE IF EXISTS product_master CASCADE;

CREATE TABLE product_master (
    product_id       VARCHAR(50) PRIMARY KEY,
    product_code     VARCHAR(50),
    product_name     VARCHAR(255),
    product_category VARCHAR(100),
    unit_price       DECIMAL(10,2),
    currency         VARCHAR(10),
    tax_rate         DECIMAL(5,2),
    status           VARCHAR(20)
);

INSERT INTO product_master (
    product_id,
    product_code,
    product_name,
    product_category,
    unit_price,
    currency,
    tax_rate,
    status
)
VALUES
('PROD-0001', '510221', 'Apple iPhone 15 Black 128GB', 'Smartphone', 1360.00, 'AUD', 10.00, 'Active'),
('PROD-0002', '610997', 'iPhone 15 Clear Case', 'Accessory', 70.00, 'AUD', 10.00, 'Active'),
('PROD-0003', '510552', 'Samsung Galaxy S23 Black 256GB', 'Smartphone', 1900.00, 'AUD', 10.00, 'Active'),
('PROD-0004', '510601', 'Samsung Galaxy Watch4 Black', 'Wearable', 600.00, 'AUD', 10.00, 'Active'),
('PROD-0005', '610331', 'Samsung S23 Case', 'Accessory', 50.00, 'AUD', 10.00, 'Active'),
('PROD-0006', '610203', 'Samsung 25W USB-C Charger', 'Accessory', 30.00, 'AUD', 10.00, 'Active');