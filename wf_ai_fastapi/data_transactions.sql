-- =========================================================
-- CLEAN RESET
-- =========================================================

DROP TABLE IF EXISTS invoice_items CASCADE;
DROP TABLE IF EXISTS invoice_header CASCADE;

DROP TABLE IF EXISTS gr_items CASCADE;
DROP TABLE IF EXISTS gr_header CASCADE;

DROP TABLE IF EXISTS po_items CASCADE;
DROP TABLE IF EXISTS po_header CASCADE;

-- =========================================================
-- 1. PURCHASE ORDER (PO)
-- =========================================================

CREATE TABLE po_header (
    id SERIAL PRIMARY KEY,
    po_number VARCHAR(50) UNIQUE,
    vendor_name VARCHAR(255),
    po_date DATE,
    total_amount NUMERIC(15,2),
    notes TEXT
);

CREATE TABLE po_items (
    id SERIAL PRIMARY KEY,
    po_id INT REFERENCES po_header(id) ON DELETE CASCADE,
    line_no INT,
    item_code VARCHAR(50),
    description TEXT,
    qty NUMERIC(15,2),
    unit_price NUMERIC(15,2),
    line_total NUMERIC(15,2),
    notes TEXT
);

-- =========================================================
-- 2. GOODS RECEIPT (GR)
-- =========================================================

CREATE TABLE gr_header (
    id SERIAL PRIMARY KEY,
    gr_number VARCHAR(50),
    po_number VARCHAR(50),
    gr_date DATE,
    notes TEXT
);

CREATE TABLE gr_items (
    id SERIAL PRIMARY KEY,
    gr_id INT REFERENCES gr_header(id) ON DELETE CASCADE,
    po_number VARCHAR(50),
    item_code VARCHAR(50),
    qty_received NUMERIC(15,2),
    warehouse VARCHAR(50),
    po_line_no INT,
    notes TEXT
);

-- =========================================================
-- 3. INVOICE (AP)
-- =========================================================

CREATE TABLE invoice_header (
    id SERIAL PRIMARY KEY,
    invoice_no VARCHAR(50),
    vendor_name VARCHAR(255),
    invoice_date DATE,
    po_number VARCHAR(50),
    total_amount NUMERIC(15,2),
    tax_amount NUMERIC(15,2),
    notes TEXT
);

CREATE TABLE invoice_items (
    id SERIAL PRIMARY KEY,
    invoice_id INT REFERENCES invoice_header(id) ON DELETE CASCADE,
    line_no INT,
    item_code VARCHAR(50),
    description TEXT,
    qty NUMERIC(15,2),
    unit_price NUMERIC(15,2),
    tax_amount NUMERIC(15,2),
    line_total NUMERIC(15,2),
    po_number VARCHAR(50),
    po_line_no INT,
    notes TEXT
);

-- =========================================================
-- 4. PURCHASE ORDERS
-- =========================================================

INSERT INTO po_header (po_number, vendor_name, po_date, total_amount, notes)
VALUES 
('PO901101', 'Fortune Global Ltd', '2023-12-01', 1573.00, 'iPhone procurement'),
('PO905507', 'Fortune Global Ltd', '2023-12-05', 2838.00, 'Samsung procurement');

-- PO 1
INSERT INTO po_items (po_id, line_no, item_code, description, qty, unit_price, line_total, notes)
VALUES
(1, 1, '510221', 'Apple iPhone 15 Black 128GB', 1, 1360, 1360, 'Base iPhone model'),
(1, 2, '610997', 'iPhone 15 Clear Case', 1, 70, 70, 'Accessory case');

-- PO 2
INSERT INTO po_items (po_id, line_no, item_code, description, qty, unit_price, line_total, notes)
VALUES
(2, 1, '510552', 'Samsung Galaxy S23 Black 256GB', 1, 1900, 1900, NULL),
(2, 2, '510601', 'Samsung Galaxy Watch4 Black', 1, 600, 600, NULL),
(2, 3, '610331', 'Samsung S23 Case', 1, 50, 50, NULL),
(2, 4, '610203', 'Samsung 25W USB-C Charger', 1, 30, 30, NULL);

-- =========================================================
-- 5. GOODS RECEIPTS
-- =========================================================

INSERT INTO gr_header (gr_number, po_number, gr_date, notes)
VALUES
('GR1001', 'PO901101', '2023-12-20', 'Partial delivery OK'),
('GR1002', 'PO905507', '2023-12-21', 'Full delivery received');

-- GR 1
INSERT INTO gr_items (gr_id, po_number, item_code, qty_received, po_line_no, notes)
VALUES
(1, 'PO901101', '510221', 1, 1, 'Received in good condition'),
(1, 'PO901101', '610997', 1, 2, 'Packed separately');

-- GR 2
INSERT INTO gr_items (gr_id, po_number, item_code, qty_received, po_line_no, notes)
VALUES
(2, 'PO905507', '510552', 1, 1, NULL),
(2, 'PO905507', '510601', 1, 2, NULL),
(2, 'PO905507', '610331', 1, 3, NULL),
(2, 'PO905507', '610203', 1, 4, NULL);

-- =========================================================
-- 6. INVOICES
-- =========================================================

-- Invoice 1
INSERT INTO invoice_header (invoice_no, vendor_name, invoice_date, po_number, total_amount, tax_amount, notes)
VALUES
('INV901101', 'Fortune Global Ltd', '2023-12-25', 'PO901101', 1573.00, 143.00, 'Standard billing');

INSERT INTO invoice_items
(invoice_id, line_no, item_code, description, qty, unit_price, tax_amount, line_total, po_number, po_line_no, notes)
VALUES
(1, 1, '510221', 'Apple iPhone 15 Black 128GB', 1, 1360, 136.00, 1496.00, 'PO901101', 1, NULL),
(1, 2, '610997', 'iPhone 15 Clear Case', 1, 70, 7.00, 77.00, 'PO901101', 2, NULL);

-- Invoice 2
INSERT INTO invoice_header (invoice_no, vendor_name, invoice_date, po_number, total_amount, tax_amount, notes)
VALUES
('INV902105', 'Fortune Global Ltd', '2023-12-18', 'PO905507', 2838.00, 258.00, 'Samsung batch invoice');

INSERT INTO invoice_items
(invoice_id, line_no, item_code, description, qty, unit_price, tax_amount, line_total, po_number, po_line_no, notes)
VALUES
(2, 1, '510552', 'Samsung Galaxy S23 Black 256GB', 1, 1900, 190.00, 2090.00, 'PO905507', 1, NULL),
(2, 2, '510601', 'Samsung Galaxy Watch4 Black', 1, 600, 60.00, 660.00, 'PO905507', 2, NULL),
(2, 3, '610331', 'Samsung S23 Case', 1, 50, 5.00, 55.00, 'PO905507', 3, NULL),
(2, 4, '610203', 'Samsung 25W USB-C Charger', 1, 30, 3.00, 33.00, 'PO905507', 4, NULL);