-- =========================================================
-- 1. ERP/CRM Output Staging Views
-- Filter only by erp_crm_documents.doc_type
-- Removed workflow_instance joins entirely
-- =========================================================
DROP VIEW IF EXISTS vw_stg_erp_direct_debit_ocr;
DROP VIEW IF EXISTS vw_stg_erp_invoice_header_ocr;
DROP VIEW IF EXISTS vw_stg_erp_invoice_items_ocr;
DROP VIEW IF EXISTS vw_stg_erp_driver_license_ocr;
DROP VIEW IF EXISTS vw_stg_erp_passport_ocr;
DROP VIEW IF EXISTS vw_stg_erp_utility_bill_ocr;

-- 🧾 1. Direct Debit
CREATE OR REPLACE VIEW vw_stg_erp_direct_debit_ocr AS
SELECT
    d.doc_id,
    d.workflow_id,
    d.reference_id,
    d.header_id,

    -- OCR FIELDS
    d.header_data->'ocr_data'->>'FirstName'     AS first_name,
    d.header_data->'ocr_data'->>'LastName'      AS last_name,
    d.header_data->'ocr_data'->>'AccountName'   AS account_name,
    d.header_data->'ocr_data'->>'AccountNumber' AS account_number,
    d.header_data->'ocr_data'->>'BSBNumber'     AS bsb,
    d.header_data->'ocr_data'->>'Email'         AS email,
    d.header_data->'ocr_data'->>'MobileNo'      AS mobile_no,
    d.header_data->'ocr_data'->>'BankName'      AS bank_name,
    d.header_data->'ocr_data'->>'BankAddress'   AS bank_address,
    d.header_data->'ocr_data'->>'HomeAddress'   AS home_address,
    d.header_data->'ocr_data'->>'SignedDate'    AS signed_date,

    -- metadata
    d.created_at,
    d.updated_at

FROM erp_crm_documents d
WHERE d.doc_type = 'direct_debit';

-- 🧾 2. Invoice Header
CREATE OR REPLACE VIEW vw_stg_erp_invoice_header_ocr AS
SELECT
    d.doc_id,
    d.workflow_id,
    d.reference_id,
    d.header_id,
    d.item_id,
    d.created_at,

    d.header_data->'ocr_data'->'documents'->0->'header'->>'InvoiceId'    AS invoice_id,
    d.header_data->'ocr_data'->'documents'->0->'header'->>'VendorName'   AS vendor_name,
    d.header_data->'ocr_data'->'documents'->0->'header'->>'CustomerName' AS customer_name,
    d.header_data->'ocr_data'->'documents'->0->'header'->>'InvoiceDate'  AS invoice_date,
    d.header_data->'ocr_data'->'documents'->0->'header'->>'InvoiceTotal' AS invoice_total_raw

FROM erp_crm_documents d
WHERE d.doc_type = 'invoice';

-- 📦 3. Invoice Items
CREATE OR REPLACE VIEW vw_stg_erp_invoice_items_ocr AS
SELECT
    d.doc_id,
    d.workflow_id,
    d.reference_id,
    d.header_id,
    d.item_id,
    d.created_at,

    d.header_data->'ocr_data'->'documents'->0->'header'->>'InvoiceId' AS invoice_id,

    item->>'Description' AS description,
    item->>'ProductCode' AS product_code,
    item->>'Quantity'    AS quantity_raw,
    item->>'UnitPrice'   AS unit_price_raw,
    item->>'Tax'         AS tax_raw,
    item->>'Amount'      AS amount_raw

FROM erp_crm_documents d

LEFT JOIN LATERAL jsonb_array_elements(
    d.header_data->'ocr_data'->'documents'->0->'items'
) item ON true

WHERE d.doc_type = 'invoice';

-- 🪪 4. Driver License
CREATE OR REPLACE VIEW vw_stg_erp_driver_license_ocr AS
SELECT
    d.doc_id,
    d.workflow_id,
    d.reference_id,
    d.header_id,
    d.item_id,

    d.header_data->'ocr_data'->>'FirstName'        AS first_name,
    d.header_data->'ocr_data'->>'LastName'         AS last_name,
    d.header_data->'ocr_data'->>'DateOfBirth'      AS date_of_birth,
    d.header_data->'ocr_data'->>'DocumentNumber'   AS license_number,
    d.header_data->'ocr_data'->>'DateOfExpiration' AS expiry_date,
    d.header_data->'ocr_data'->>'issuedBy'         AS issued_by,
    d.header_data->'ocr_data'->>'Address'          AS address,

    d.header_data->>'document_url' AS document_url,
    (d.header_data->>'confidence')::float AS confidence,
    d.header_data->>'validation_status' AS validation_status,

    d.created_at,
    d.updated_at

FROM erp_crm_documents d
WHERE d.doc_type = 'driver_license';

-- 🛂 5. Passport View
CREATE OR REPLACE VIEW vw_stg_erp_passport_ocr AS
SELECT
    d.doc_id,
    d.workflow_id,
    d.reference_id,
    d.header_id,
    d.item_id,

    d.header_data->'ocr_data'->>'FirstName'        AS first_name,
    d.header_data->'ocr_data'->>'LastName'         AS last_name,
    d.header_data->'ocr_data'->>'DateOfBirth'      AS date_of_birth,
    d.header_data->'ocr_data'->>'Sex'              AS gender,

    d.header_data->'ocr_data'->>'DocumentNumber'   AS passport_number,
    d.header_data->'ocr_data'->>'Nationality'      AS nationality,
    d.header_data->'ocr_data'->>'Country'          AS country,
    d.header_data->'ocr_data'->>'DateOfIssue'      AS issue_date,
    d.header_data->'ocr_data'->>'DateOfExpiration' AS expiry_date,
    d.header_data->'ocr_data'->>'PlaceOfBirth'     AS place_of_birth,

    d.header_data->>'document_url' AS document_url,
    (d.header_data->>'confidence')::float AS confidence,
    d.header_data->>'validation_status' AS validation_status,

    d.created_at,
    d.updated_at

FROM erp_crm_documents d
WHERE d.doc_type = 'passport';

-- 💡 6. Utility Bill View
CREATE OR REPLACE VIEW vw_stg_erp_utility_bill_ocr AS
SELECT
    d.doc_id,
    d.workflow_id,
    d.reference_id,
    d.header_id,
    d.item_id,

    d.header_data->'ocr_data'->>'address'        AS full_address,
    d.header_data->'ocr_data'->>'account_number' AS account_number,
    d.header_data->'ocr_data'->>'retailer'       AS provider,
    d.header_data->'ocr_data'->>'issue_date'     AS issue_date,

    d.header_data->>'document_url' AS document_url,
    (d.header_data->>'confidence')::float AS confidence,
    d.header_data->>'validation_status' AS validation_status,

    d.created_at,
    d.updated_at

FROM erp_crm_documents d
WHERE d.doc_type = 'utility_bill';