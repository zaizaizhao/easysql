-- ============================================================================
-- 02_test_data.sql
-- Seed data for US e-commerce product demo
-- ============================================================================

-- 1) US state tax reference (base rates, simplified)
INSERT INTO us_state_tax (state_code, state_name, sales_tax_rate) VALUES
('CA', 'California', 0.0725),
('NY', 'New York', 0.0400),
('TX', 'Texas', 0.0625),
('FL', 'Florida', 0.0600),
('WA', 'Washington', 0.0650),
('IL', 'Illinois', 0.0625),
('MA', 'Massachusetts', 0.0625),
('NJ', 'New Jersey', 0.0663),
('CO', 'Colorado', 0.0290),
('AZ', 'Arizona', 0.0560);

-- 2) Customers
INSERT INTO customer (first_name, last_name, email, phone, customer_segment, created_at) VALUES
('Emma', 'Johnson', 'emma.johnson@example.com', '415-555-0110', 'vip', '2024-02-18 10:00:00'),
('Liam', 'Smith', 'liam.smith@example.com', '213-555-0121', 'loyal', '2024-03-04 13:20:00'),
('Olivia', 'Williams', 'olivia.williams@example.com', '206-555-0132', 'new', '2024-06-19 09:45:00'),
('Noah', 'Brown', 'noah.brown@example.com', '512-555-0143', 'business', '2023-12-10 16:30:00'),
('Ava', 'Jones', 'ava.jones@example.com', '469-555-0154', 'loyal', '2024-07-22 11:10:00'),
('Ethan', 'Garcia', 'ethan.garcia@example.com', '305-555-0165', 'new', '2025-01-08 08:55:00'),
('Sophia', 'Miller', 'sophia.miller@example.com', '407-555-0176', 'new', '2025-02-14 15:40:00'),
('Mason', 'Davis', 'mason.davis@example.com', '917-555-0187', 'vip', '2023-11-21 12:25:00'),
('Isabella', 'Rodriguez', 'isabella.rodriguez@example.com', '718-555-0198', 'loyal', '2024-04-29 17:05:00'),
('Lucas', 'Martinez', 'lucas.martinez@example.com', '312-555-0209', 'business', '2024-08-11 14:15:00'),
('Mia', 'Hernandez', 'mia.hernandez@example.com', '617-555-0211', 'new', '2025-03-03 09:05:00'),
('James', 'Lopez', 'james.lopez@example.com', '201-555-0222', 'loyal', '2024-09-15 18:20:00'),
('Charlotte', 'Gonzalez', 'charlotte.gonzalez@example.com', '303-555-0233', 'vip', '2024-01-12 10:35:00'),
('Benjamin', 'Wilson', 'benjamin.wilson@example.com', '602-555-0244', 'new', '2025-05-01 13:50:00'),
('Amelia', 'Anderson', 'amelia.anderson@example.com', '619-555-0255', 'loyal', '2023-10-07 11:30:00'),
('Elijah', 'Thomas', 'elijah.thomas@example.com', '281-555-0266', 'business', '2024-05-18 16:05:00'),
('Harper', 'Taylor', 'harper.taylor@example.com', '813-555-0277', 'new', '2025-06-09 07:45:00'),
('Henry', 'Moore', 'henry.moore@example.com', '425-555-0288', 'vip', '2024-02-27 12:40:00'),
('Evelyn', 'Jackson', 'evelyn.jackson@example.com', '551-555-0299', 'loyal', '2024-12-30 15:15:00'),
('Alexander', 'Martin', 'alexander.martin@example.com', '617-555-0300', 'business', '2025-01-27 09:30:00'),
('Abigail', 'Lee', 'abigail.lee@example.com', '972-555-0311', 'new', '2025-04-06 14:25:00'),
('Michael', 'Perez', 'michael.perez@example.com', '916-555-0322', 'loyal', '2024-11-14 11:45:00'),
('Emily', 'Thompson', 'emily.thompson@example.com', '720-555-0333', 'new', '2025-05-25 17:10:00'),
('Daniel', 'White', 'daniel.white@example.com', '480-555-0344', 'vip', '2024-06-01 10:50:00');

-- 3) Addresses (one default shipping+billing address per customer)
INSERT INTO customer_address (
    customer_id,
    recipient_name,
    line1,
    line2,
    city,
    state_code,
    postal_code,
    is_default_shipping,
    is_default_billing
) VALUES
(1, 'Emma Johnson', '425 Market St', 'Apt 1204', 'San Francisco', 'CA', '94103', TRUE, TRUE),
(2, 'Liam Smith', '888 S Hope St', NULL, 'Los Angeles', 'CA', '90017', TRUE, TRUE),
(3, 'Olivia Williams', '1420 5th Ave', 'Unit 502', 'Seattle', 'WA', '98101', TRUE, TRUE),
(4, 'Noah Brown', '110 Congress Ave', 'Suite 410', 'Austin', 'TX', '78701', TRUE, TRUE),
(5, 'Ava Jones', '2323 Ross Ave', NULL, 'Dallas', 'TX', '75201', TRUE, TRUE),
(6, 'Ethan Garcia', '701 Brickell Ave', NULL, 'Miami', 'FL', '33131', TRUE, TRUE),
(7, 'Sophia Miller', '121 S Orange Ave', 'Unit 830', 'Orlando', 'FL', '32801', TRUE, TRUE),
(8, 'Mason Davis', '450 W 33rd St', 'Floor 9', 'New York', 'NY', '10001', TRUE, TRUE),
(9, 'Isabella Rodriguez', '325 Jay St', NULL, 'Brooklyn', 'NY', '11201', TRUE, TRUE),
(10, 'Lucas Martinez', '233 S Wacker Dr', 'Suite 2800', 'Chicago', 'IL', '60606', TRUE, TRUE),
(11, 'Mia Hernandez', '100 Cambridge St', NULL, 'Boston', 'MA', '02114', TRUE, TRUE),
(12, 'James Lopez', '30 Hudson St', 'Apt 7B', 'Jersey City', 'NJ', '07302', TRUE, TRUE),
(13, 'Charlotte Gonzalez', '1700 Broadway', 'Suite 1500', 'Denver', 'CO', '80202', TRUE, TRUE),
(14, 'Benjamin Wilson', '2 N Central Ave', NULL, 'Phoenix', 'AZ', '85004', TRUE, TRUE),
(15, 'Amelia Anderson', '655 W Broadway', NULL, 'San Diego', 'CA', '92101', TRUE, TRUE),
(16, 'Elijah Thomas', '700 Louisiana St', 'Suite 1400', 'Houston', 'TX', '77002', TRUE, TRUE),
(17, 'Harper Taylor', '100 N Tampa St', NULL, 'Tampa', 'FL', '33602', TRUE, TRUE),
(18, 'Henry Moore', '500 108th Ave NE', NULL, 'Bellevue', 'WA', '98004', TRUE, TRUE),
(19, 'Evelyn Jackson', '80 River St', NULL, 'Hoboken', 'NJ', '07030', TRUE, TRUE),
(20, 'Alexander Martin', '1 Main St', NULL, 'Cambridge', 'MA', '02142', TRUE, TRUE),
(21, 'Abigail Lee', '5800 Legacy Dr', NULL, 'Plano', 'TX', '75024', TRUE, TRUE),
(22, 'Michael Perez', '500 Capitol Mall', NULL, 'Sacramento', 'CA', '95814', TRUE, TRUE),
(23, 'Emily Thompson', '1200 Pearl St', NULL, 'Boulder', 'CO', '80302', TRUE, TRUE),
(24, 'Daniel White', '7135 E Camelback Rd', 'Suite 220', 'Scottsdale', 'AZ', '85251', TRUE, TRUE);

-- 4) Catalog references
INSERT INTO brand (brand_name, country_of_origin) VALUES
('Apple', 'United States'),
('Samsung', 'South Korea'),
('Sony', 'Japan'),
('Bose', 'United States'),
('Logitech', 'Switzerland'),
('Anker', 'China'),
('Ninja', 'United States'),
('Instant Pot', 'Canada'),
('Dyson', 'United Kingdom'),
('Garmin', 'United States'),
('HP', 'United States'),
('Dell', 'United States');

INSERT INTO category (category_name) VALUES
('Electronics'),
('Home & Kitchen'),
('Fitness'),
('Office Supplies');

INSERT INTO category (category_name, parent_category_id) VALUES
('Smartphones', (SELECT category_id FROM category WHERE category_name = 'Electronics')),
('Audio', (SELECT category_id FROM category WHERE category_name = 'Electronics')),
('Laptops', (SELECT category_id FROM category WHERE category_name = 'Electronics')),
('Displays', (SELECT category_id FROM category WHERE category_name = 'Electronics')),
('Computer Accessories', (SELECT category_id FROM category WHERE category_name = 'Electronics')),
('Mobile Accessories', (SELECT category_id FROM category WHERE category_name = 'Electronics')),
('Small Appliances', (SELECT category_id FROM category WHERE category_name = 'Home & Kitchen')),
('Cleaning', (SELECT category_id FROM category WHERE category_name = 'Home & Kitchen')),
('Wearables', (SELECT category_id FROM category WHERE category_name = 'Fitness'));

INSERT INTO product (
    sku,
    product_name,
    brand_id,
    category_id,
    unit_cost,
    list_price,
    msrp,
    launch_date,
    is_active
) VALUES
(
    'APL-IP15-128-BLK',
    'Apple iPhone 15 128GB Unlocked',
    (SELECT brand_id FROM brand WHERE brand_name = 'Apple'),
    (SELECT category_id FROM category WHERE category_name = 'Smartphones'),
    620.00,
    799.00,
    799.00,
    '2024-09-20',
    TRUE
),
(
    'SMS-S24-128-GRY',
    'Samsung Galaxy S24 128GB Unlocked',
    (SELECT brand_id FROM brand WHERE brand_name = 'Samsung'),
    (SELECT category_id FROM category WHERE category_name = 'Smartphones'),
    610.00,
    799.00,
    799.00,
    '2024-01-31',
    TRUE
),
(
    'SNY-WH1000XM5-BLK',
    'Sony WH-1000XM5 Noise Cancelling Headphones',
    (SELECT brand_id FROM brand WHERE brand_name = 'Sony'),
    (SELECT category_id FROM category WHERE category_name = 'Audio'),
    255.00,
    399.00,
    399.00,
    '2023-07-15',
    TRUE
),
(
    'BSE-QCU-HPHN-BLK',
    'Bose QuietComfort Ultra Headphones',
    (SELECT brand_id FROM brand WHERE brand_name = 'Bose'),
    (SELECT category_id FROM category WHERE category_name = 'Audio'),
    275.00,
    429.00,
    429.00,
    '2024-10-05',
    TRUE
),
(
    'APL-APP2-WHT',
    'Apple AirPods Pro 2nd Gen',
    (SELECT brand_id FROM brand WHERE brand_name = 'Apple'),
    (SELECT category_id FROM category WHERE category_name = 'Audio'),
    155.00,
    249.00,
    249.00,
    '2023-11-11',
    TRUE
),
(
    'LOG-MX3S-MSE',
    'Logitech MX Master 3S Mouse',
    (SELECT brand_id FROM brand WHERE brand_name = 'Logitech'),
    (SELECT category_id FROM category WHERE category_name = 'Computer Accessories'),
    55.00,
    99.00,
    109.00,
    '2023-10-02',
    TRUE
),
(
    'LOG-MXKEYS-S',
    'Logitech MX Keys S Keyboard',
    (SELECT brand_id FROM brand WHERE brand_name = 'Logitech'),
    (SELECT category_id FROM category WHERE category_name = 'Computer Accessories'),
    60.00,
    109.00,
    119.00,
    '2024-02-14',
    TRUE
),
(
    'ANK-737-PBANK',
    'Anker 737 Power Bank 24000mAh',
    (SELECT brand_id FROM brand WHERE brand_name = 'Anker'),
    (SELECT category_id FROM category WHERE category_name = 'Mobile Accessories'),
    90.00,
    149.00,
    159.00,
    '2024-03-22',
    TRUE
),
(
    'DEL-U2722DC-MON',
    'Dell UltraSharp 27-inch USB-C Monitor',
    (SELECT brand_id FROM brand WHERE brand_name = 'Dell'),
    (SELECT category_id FROM category WHERE category_name = 'Displays'),
    230.00,
    349.00,
    379.00,
    '2024-08-01',
    TRUE
),
(
    'HP-LJ4101FDW',
    'HP LaserJet Pro MFP 4101fdw',
    (SELECT brand_id FROM brand WHERE brand_name = 'HP'),
    (SELECT category_id FROM category WHERE category_name = 'Office Supplies'),
    320.00,
    499.00,
    529.00,
    '2023-09-09',
    TRUE
),
(
    'NJA-BLEND-BN701',
    'Ninja Professional Blender BN701',
    (SELECT brand_id FROM brand WHERE brand_name = 'Ninja'),
    (SELECT category_id FROM category WHERE category_name = 'Small Appliances'),
    68.00,
    119.00,
    129.00,
    '2024-05-16',
    TRUE
),
(
    'INS-DUO-6QT',
    'Instant Pot Duo 7-in-1 6qt',
    (SELECT brand_id FROM brand WHERE brand_name = 'Instant Pot'),
    (SELECT category_id FROM category WHERE category_name = 'Small Appliances'),
    52.00,
    99.00,
    119.00,
    '2024-01-18',
    TRUE
),
(
    'DYS-V8-CORDLESS',
    'Dyson V8 Cordless Vacuum',
    (SELECT brand_id FROM brand WHERE brand_name = 'Dyson'),
    (SELECT category_id FROM category WHERE category_name = 'Cleaning'),
    250.00,
    399.00,
    449.00,
    '2024-04-12',
    TRUE
),
(
    'GAR-FR265-BLK',
    'Garmin Forerunner 265',
    (SELECT brand_id FROM brand WHERE brand_name = 'Garmin'),
    (SELECT category_id FROM category WHERE category_name = 'Wearables'),
    290.00,
    449.00,
    449.00,
    '2024-09-07',
    TRUE
),
(
    'GAR-VENU3-SLT',
    'Garmin Venu 3',
    (SELECT brand_id FROM brand WHERE brand_name = 'Garmin'),
    (SELECT category_id FROM category WHERE category_name = 'Wearables'),
    285.00,
    449.00,
    449.00,
    '2024-10-15',
    TRUE
),
(
    'APL-WATCH10-41',
    'Apple Watch Series 10 GPS 41mm',
    (SELECT brand_id FROM brand WHERE brand_name = 'Apple'),
    (SELECT category_id FROM category WHERE category_name = 'Wearables'),
    250.00,
    399.00,
    399.00,
    '2024-09-20',
    TRUE
),
(
    'SMS-Q70D-55',
    'Samsung 55-inch QLED 4K TV Q70D',
    (SELECT brand_id FROM brand WHERE brand_name = 'Samsung'),
    (SELECT category_id FROM category WHERE category_name = 'Electronics'),
    640.00,
    899.00,
    999.00,
    '2024-06-10',
    TRUE
),
(
    'ANK-100W-CHARGER',
    'Anker 100W USB-C Charger',
    (SELECT brand_id FROM brand WHERE brand_name = 'Anker'),
    (SELECT category_id FROM category WHERE category_name = 'Mobile Accessories'),
    32.00,
    69.00,
    79.00,
    '2024-03-01',
    TRUE
),
(
    'DEL-XPS13-2025',
    'Dell XPS 13 Laptop 2025',
    (SELECT brand_id FROM brand WHERE brand_name = 'Dell'),
    (SELECT category_id FROM category WHERE category_name = 'Laptops'),
    980.00,
    1299.00,
    1399.00,
    '2025-01-15',
    TRUE
),
(
    'HP-ENVY16-2025',
    'HP Envy 16 Laptop 2025',
    (SELECT brand_id FROM brand WHERE brand_name = 'HP'),
    (SELECT category_id FROM category WHERE category_name = 'Laptops'),
    1040.00,
    1399.00,
    1499.00,
    '2025-02-11',
    TRUE
);

-- 5) Warehouses and inventory snapshots
INSERT INTO warehouse (warehouse_code, warehouse_name, city, state_code) VALUES
('W-CA01', 'West Coast Fulfillment Center', 'Fremont', 'CA'),
('W-TX01', 'Central Distribution Center', 'Dallas', 'TX'),
('W-NJ01', 'East Coast Logistics Hub', 'Newark', 'NJ');

INSERT INTO inventory (
    warehouse_id,
    product_id,
    on_hand_qty,
    reserved_qty,
    reorder_point,
    last_restocked_at
)
SELECT
    w.warehouse_id,
    p.product_id,
    CASE
        WHEN w.warehouse_code = 'W-CA01' THEN 120 + (p.product_id * 7) % 90
        WHEN w.warehouse_code = 'W-TX01' THEN 100 + (p.product_id * 11) % 110
        ELSE 80 + (p.product_id * 13) % 70
    END AS on_hand_qty,
    0 AS reserved_qty,
    CASE
        WHEN p.list_price >= 800 THEN 8
        WHEN p.list_price >= 300 THEN 15
        ELSE 25
    END AS reorder_point,
    TIMESTAMP '2026-01-20 08:00:00' - ((p.product_id + w.warehouse_id) * INTERVAL '2 days')
FROM warehouse w
CROSS JOIN product p;

-- 6) Orders across holiday season + Q1 (US market behavior)
WITH seq AS (
    SELECT
        n,
        TIMESTAMP '2025-09-01 09:00:00'
            + (n * INTERVAL '2 days')
            + ((n % 6) * INTERVAL '3 hours') AS order_ts
    FROM generate_series(1, 72) AS n
)
INSERT INTO orders (
    order_number,
    customer_id,
    order_date,
    order_status,
    payment_status,
    shipping_address_id,
    billing_address_id,
    channel
)
SELECT
    'US-' || to_char(order_ts, 'YYYY') || '-' || lpad(n::text, 5, '0') AS order_number,
    ((n - 1) % 24) + 1 AS customer_id,
    order_ts,
    CASE
        WHEN n % 17 = 0 THEN 'RETURNED'
        WHEN n % 13 = 0 THEN 'CANCELLED'
        WHEN n % 4 = 0 THEN 'SHIPPED'
        ELSE 'DELIVERED'
    END AS order_status,
    CASE
        WHEN n % 13 = 0 THEN 'REFUNDED'
        WHEN n % 9 = 0 THEN 'PENDING'
        ELSE 'PAID'
    END AS payment_status,
    ((n - 1) % 24) + 1 AS shipping_address_id,
    ((n - 1) % 24) + 1 AS billing_address_id,
    CASE
        WHEN n % 5 = 0 THEN 'marketplace'
        WHEN n % 2 = 0 THEN 'mobile'
        ELSE 'web'
    END AS channel
FROM seq;

-- 7) Order items with state-dependent tax and promotional windows
INSERT INTO order_item (
    order_id,
    product_id,
    quantity,
    unit_price,
    discount_amount,
    tax_amount,
    line_total
)
SELECT
    o.order_id,
    p.product_id,
    qty.quantity,
    p.list_price,
    price_calc.discount_amount,
    price_calc.tax_amount,
    price_calc.line_total
FROM orders o
JOIN customer_address a ON a.address_id = o.shipping_address_id
JOIN us_state_tax st ON st.state_code = a.state_code
JOIN LATERAL generate_series(
    1,
    CASE
        WHEN o.order_id % 6 = 0 THEN 3
        WHEN o.order_id % 2 = 0 THEN 2
        ELSE 1
    END
) AS item_idx(n) ON TRUE
JOIN product p ON p.product_id = ((o.order_id * 7 + item_idx.n * 5) % 20) + 1
JOIN LATERAL (
    SELECT
        CASE
            WHEN p.list_price >= 1200 THEN 1
            WHEN p.list_price >= 400 THEN CASE WHEN o.order_id % 4 = 0 THEN 2 ELSE 1 END
            ELSE CASE WHEN o.order_id % 5 = 0 THEN 3 ELSE 2 END
        END AS quantity
) AS qty ON TRUE
JOIN LATERAL (
    SELECT
        CASE
            WHEN o.order_date::date BETWEEN DATE '2025-11-24' AND DATE '2025-12-02' THEN 0.15
            WHEN o.order_date::date BETWEEN DATE '2025-12-15' AND DATE '2025-12-24' THEN 0.08
            WHEN o.channel = 'marketplace' THEN 0.05
            ELSE 0.00
        END AS discount_rate
) AS promo ON TRUE
JOIN LATERAL (
    SELECT
        round((qty.quantity * p.list_price) * promo.discount_rate, 2) AS discount_amount,
        round(
            (
                (qty.quantity * p.list_price)
                - round((qty.quantity * p.list_price) * promo.discount_rate, 2)
            ) * st.sales_tax_rate,
            2
        ) AS tax_amount,
        round(
            (qty.quantity * p.list_price)
            - round((qty.quantity * p.list_price) * promo.discount_rate, 2)
            + round(
                (
                    (qty.quantity * p.list_price)
                    - round((qty.quantity * p.list_price) * promo.discount_rate, 2)
                ) * st.sales_tax_rate,
                2
            ),
            2
        ) AS line_total
) AS price_calc ON TRUE;

-- 8) Roll up order totals
WITH line_sums AS (
    SELECT
        oi.order_id,
        round(sum(oi.quantity * oi.unit_price), 2) AS subtotal,
        round(sum(oi.discount_amount), 2) AS discount_amount,
        round(sum(oi.tax_amount), 2) AS tax_amount
    FROM order_item oi
    GROUP BY oi.order_id
)
UPDATE orders o
SET
    subtotal = ls.subtotal,
    discount_amount = ls.discount_amount,
    tax_amount = ls.tax_amount,
    shipping_fee = CASE
        WHEN o.order_status = 'CANCELLED' THEN 0
        WHEN ls.subtotal >= 300 THEN 0
        WHEN ls.subtotal >= 100 THEN 4.99
        ELSE 8.99
    END,
    total_amount = round(
        ls.subtotal
        - ls.discount_amount
        + ls.tax_amount
        + CASE
            WHEN o.order_status = 'CANCELLED' THEN 0
            WHEN ls.subtotal >= 300 THEN 0
            WHEN ls.subtotal >= 100 THEN 4.99
            ELSE 8.99
        END,
        2
    )
FROM line_sums ls
WHERE o.order_id = ls.order_id;

-- 9) Payments
WITH pay_source AS (
    SELECT
        o.order_id,
        o.order_date,
        o.order_status,
        o.payment_status,
        o.total_amount,
        CASE
            WHEN o.order_id % 10 = 0 THEN 'gift_card'
            WHEN o.order_id % 7 = 0 THEN 'apple_pay'
            WHEN o.order_id % 5 = 0 THEN 'paypal'
            WHEN o.order_id % 9 = 0 THEN 'affirm'
            ELSE 'card'
        END AS payment_method
    FROM orders o
)
INSERT INTO payment (
    order_id,
    payment_method,
    payment_provider,
    card_network,
    amount,
    paid_at,
    payment_status
)
SELECT
    p.order_id,
    p.payment_method,
    CASE p.payment_method
        WHEN 'paypal' THEN 'PayPal'
        WHEN 'apple_pay' THEN 'Apple Pay'
        WHEN 'affirm' THEN 'Affirm'
        WHEN 'gift_card' THEN 'Gift Card'
        ELSE 'Stripe'
    END AS payment_provider,
    CASE
        WHEN p.payment_method = 'card' THEN
            CASE p.order_id % 4
                WHEN 0 THEN 'visa'
                WHEN 1 THEN 'mastercard'
                WHEN 2 THEN 'amex'
                ELSE 'discover'
            END
        ELSE NULL
    END AS card_network,
    p.total_amount,
    CASE
        WHEN p.payment_status IN ('PAID', 'REFUNDED') THEN p.order_date + INTERVAL '2 hours'
        ELSE NULL
    END AS paid_at,
    CASE p.payment_status
        WHEN 'PAID' THEN 'captured'
        WHEN 'REFUNDED' THEN 'refunded'
        WHEN 'PENDING' THEN 'pending'
        ELSE 'failed'
    END AS payment_status
FROM pay_source p;

-- 10) Shipments for orders that entered fulfillment
WITH wh AS (
    SELECT
        max(CASE WHEN warehouse_code = 'W-CA01' THEN warehouse_id END) AS west_id,
        max(CASE WHEN warehouse_code = 'W-TX01' THEN warehouse_id END) AS central_id,
        max(CASE WHEN warehouse_code = 'W-NJ01' THEN warehouse_id END) AS east_id
    FROM warehouse
)
INSERT INTO shipment (
    order_id,
    warehouse_id,
    carrier,
    service_level,
    tracking_number,
    shipped_at,
    delivered_at,
    shipping_cost,
    shipping_status
)
SELECT
    o.order_id,
    CASE
        WHEN a.state_code IN ('CA', 'WA', 'AZ', 'CO') THEN wh.west_id
        WHEN a.state_code IN ('TX', 'FL', 'IL') THEN wh.central_id
        ELSE wh.east_id
    END AS warehouse_id,
    CASE
        WHEN o.order_id % 3 = 0 THEN 'FedEx'
        WHEN o.order_id % 4 = 0 THEN 'USPS'
        ELSE 'UPS'
    END AS carrier,
    CASE
        WHEN o.total_amount >= 1000 THEN 'overnight'
        WHEN o.total_amount >= 250 THEN 'two_day'
        ELSE 'ground'
    END AS service_level,
    'TRK-' || lpad(o.order_id::text, 8, '0') AS tracking_number,
    o.order_date + INTERVAL '1 day' + ((o.order_id % 5) * INTERVAL '2 hours') AS shipped_at,
    CASE
        WHEN o.order_status IN ('DELIVERED', 'RETURNED') THEN
            o.order_date + INTERVAL '4 days' + ((o.order_id % 3) * INTERVAL '8 hours')
        ELSE NULL
    END AS delivered_at,
    CASE
        WHEN o.total_amount >= 500 THEN 12.99
        WHEN o.total_amount >= 200 THEN 8.99
        ELSE 5.49
    END AS shipping_cost,
    CASE o.order_status
        WHEN 'SHIPPED' THEN 'in_transit'
        WHEN 'DELIVERED' THEN 'delivered'
        WHEN 'RETURNED' THEN 'returned'
        ELSE 'label_created'
    END AS shipping_status
FROM orders o
JOIN customer_address a ON a.address_id = o.shipping_address_id
CROSS JOIN wh
WHERE o.order_status IN ('SHIPPED', 'DELIVERED', 'RETURNED');

-- 11) Product reviews from a subset of delivered orders
WITH ranked_items AS (
    SELECT
        oi.order_item_id,
        o.order_id,
        o.order_date,
        row_number() OVER (PARTITION BY o.order_id ORDER BY oi.order_item_id) AS rn
    FROM orders o
    JOIN order_item oi ON oi.order_id = o.order_id
    WHERE o.order_status = 'DELIVERED'
)
INSERT INTO product_review (
    order_item_id,
    rating,
    review_title,
    review_text,
    helpful_votes,
    created_at
)
SELECT
    ri.order_item_id,
    CASE
        WHEN ri.order_id % 9 = 0 THEN 3
        WHEN ri.order_id % 4 = 0 THEN 4
        ELSE 5
    END AS rating,
    CASE
        WHEN ri.order_id % 9 = 0 THEN 'Good value but room to improve'
        WHEN ri.order_id % 4 = 0 THEN 'Solid product for daily use'
        ELSE 'Excellent purchase and fast delivery'
    END AS review_title,
    CASE
        WHEN ri.order_id % 9 = 0 THEN
            'The product works as expected, but the setup took longer than I hoped.'
        WHEN ri.order_id % 4 = 0 THEN
            'Quality is good and packaging was secure. I would recommend it.'
        ELSE
            'Great performance and exactly as described. I would buy again.'
    END AS review_text,
    ri.order_id % 48 AS helpful_votes,
    ri.order_date + INTERVAL '12 days' AS created_at
FROM ranked_items ri
WHERE ri.rn = 1 AND ri.order_id % 2 = 0;

-- 12) Returns for orders marked as returned
WITH returned_items AS (
    SELECT
        oi.order_item_id,
        o.order_id,
        o.order_date,
        oi.line_total,
        row_number() OVER (PARTITION BY o.order_id ORDER BY oi.line_total DESC) AS rn
    FROM orders o
    JOIN order_item oi ON oi.order_id = o.order_id
    WHERE o.order_status = 'RETURNED'
)
INSERT INTO return_request (
    order_item_id,
    return_reason,
    return_status,
    requested_at,
    approved_at,
    refunded_amount
)
SELECT
    ri.order_item_id,
    CASE ri.order_id % 3
        WHEN 0 THEN 'Damaged on arrival'
        WHEN 1 THEN 'Wrong item shipped'
        ELSE 'Not as described'
    END AS return_reason,
    'refunded' AS return_status,
    ri.order_date + INTERVAL '7 days' AS requested_at,
    ri.order_date + INTERVAL '9 days' AS approved_at,
    ri.line_total AS refunded_amount
FROM returned_items ri
WHERE ri.rn = 1;

-- 13) Reserve inventory based on open demand
WITH wh AS (
    SELECT
        max(CASE WHEN warehouse_code = 'W-CA01' THEN warehouse_id END) AS west_id,
        max(CASE WHEN warehouse_code = 'W-TX01' THEN warehouse_id END) AS central_id,
        max(CASE WHEN warehouse_code = 'W-NJ01' THEN warehouse_id END) AS east_id
    FROM warehouse
),
order_demand AS (
    SELECT
        CASE
            WHEN a.state_code IN ('CA', 'WA', 'AZ', 'CO') THEN wh.west_id
            WHEN a.state_code IN ('TX', 'FL', 'IL') THEN wh.central_id
            ELSE wh.east_id
        END AS warehouse_id,
        oi.product_id,
        sum(oi.quantity) AS demand_qty
    FROM orders o
    JOIN customer_address a ON a.address_id = o.shipping_address_id
    JOIN order_item oi ON oi.order_id = o.order_id
    CROSS JOIN wh
    WHERE o.order_status IN ('PENDING', 'PAID', 'SHIPPED')
    GROUP BY 1, oi.product_id
)
UPDATE inventory i
SET reserved_qty = LEAST(i.on_hand_qty, od.demand_qty)
FROM order_demand od
WHERE i.warehouse_id = od.warehouse_id AND i.product_id = od.product_id;
