-- ============================================================================
-- 01_schema.sql
-- Product demo schema (PostgreSQL)
-- US-market e-commerce domain for English hackathon demos
-- ============================================================================

-- 1) Geography and tax references
CREATE TABLE us_state_tax (
    state_code CHAR(2) PRIMARY KEY,
    state_name VARCHAR(64) NOT NULL,
    sales_tax_rate NUMERIC(5, 4) NOT NULL CHECK (sales_tax_rate >= 0 AND sales_tax_rate <= 0.15)
);

-- 2) Customer domain
CREATE TABLE customer (
    customer_id SERIAL PRIMARY KEY,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    phone VARCHAR(25),
    customer_segment VARCHAR(20) NOT NULL DEFAULT 'new'
        CHECK (customer_segment IN ('new', 'loyal', 'vip', 'business')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE customer_address (
    address_id SERIAL PRIMARY KEY,
    customer_id INT NOT NULL REFERENCES customer(customer_id),
    recipient_name VARCHAR(100) NOT NULL,
    line1 VARCHAR(120) NOT NULL,
    line2 VARCHAR(120),
    city VARCHAR(80) NOT NULL,
    state_code CHAR(2) NOT NULL REFERENCES us_state_tax(state_code),
    postal_code VARCHAR(10) NOT NULL,
    is_default_shipping BOOLEAN NOT NULL DEFAULT FALSE,
    is_default_billing BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX idx_customer_address_customer ON customer_address(customer_id);
CREATE INDEX idx_customer_address_state ON customer_address(state_code);

-- 3) Product catalog
CREATE TABLE brand (
    brand_id SERIAL PRIMARY KEY,
    brand_name VARCHAR(100) NOT NULL UNIQUE,
    country_of_origin VARCHAR(100) NOT NULL
);

CREATE TABLE category (
    category_id SERIAL PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL UNIQUE,
    parent_category_id INT REFERENCES category(category_id)
);

CREATE TABLE product (
    product_id SERIAL PRIMARY KEY,
    sku VARCHAR(32) NOT NULL UNIQUE,
    product_name VARCHAR(150) NOT NULL,
    brand_id INT NOT NULL REFERENCES brand(brand_id),
    category_id INT NOT NULL REFERENCES category(category_id),
    unit_cost NUMERIC(10, 2) NOT NULL CHECK (unit_cost >= 0),
    list_price NUMERIC(10, 2) NOT NULL CHECK (list_price >= 0),
    msrp NUMERIC(10, 2) NOT NULL CHECK (msrp >= 0),
    launch_date DATE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX idx_product_category ON product(category_id);
CREATE INDEX idx_product_brand ON product(brand_id);

-- 4) Warehouse and inventory
CREATE TABLE warehouse (
    warehouse_id SERIAL PRIMARY KEY,
    warehouse_code VARCHAR(20) NOT NULL UNIQUE,
    warehouse_name VARCHAR(100) NOT NULL,
    city VARCHAR(80) NOT NULL,
    state_code CHAR(2) NOT NULL REFERENCES us_state_tax(state_code)
);

CREATE TABLE inventory (
    warehouse_id INT NOT NULL REFERENCES warehouse(warehouse_id),
    product_id INT NOT NULL REFERENCES product(product_id),
    on_hand_qty INT NOT NULL DEFAULT 0 CHECK (on_hand_qty >= 0),
    reserved_qty INT NOT NULL DEFAULT 0 CHECK (reserved_qty >= 0),
    reorder_point INT NOT NULL DEFAULT 10 CHECK (reorder_point >= 0),
    last_restocked_at TIMESTAMP,
    PRIMARY KEY (warehouse_id, product_id)
);
CREATE INDEX idx_inventory_product ON inventory(product_id);

-- 5) Order lifecycle
CREATE TABLE orders (
    order_id BIGSERIAL PRIMARY KEY,
    order_number VARCHAR(30) NOT NULL UNIQUE,
    customer_id INT NOT NULL REFERENCES customer(customer_id),
    order_date TIMESTAMP NOT NULL,
    order_status VARCHAR(20) NOT NULL CHECK (
        order_status IN ('PENDING', 'PAID', 'SHIPPED', 'DELIVERED', 'CANCELLED', 'RETURNED')
    ),
    payment_status VARCHAR(20) NOT NULL CHECK (
        payment_status IN ('PENDING', 'PAID', 'REFUNDED', 'FAILED')
    ),
    shipping_address_id INT NOT NULL REFERENCES customer_address(address_id),
    billing_address_id INT NOT NULL REFERENCES customer_address(address_id),
    channel VARCHAR(20) NOT NULL CHECK (channel IN ('web', 'mobile', 'marketplace')),
    subtotal NUMERIC(12, 2) NOT NULL DEFAULT 0,
    discount_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
    tax_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
    shipping_fee NUMERIC(12, 2) NOT NULL DEFAULT 0,
    total_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
    currency CHAR(3) NOT NULL DEFAULT 'USD'
);
CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_date ON orders(order_date);
CREATE INDEX idx_orders_status ON orders(order_status);

CREATE TABLE order_item (
    order_item_id BIGSERIAL PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    product_id INT NOT NULL REFERENCES product(product_id),
    quantity INT NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(10, 2) NOT NULL CHECK (unit_price >= 0),
    discount_amount NUMERIC(10, 2) NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
    tax_amount NUMERIC(10, 2) NOT NULL DEFAULT 0 CHECK (tax_amount >= 0),
    line_total NUMERIC(12, 2) NOT NULL CHECK (line_total >= 0)
);
CREATE INDEX idx_order_item_order ON order_item(order_id);
CREATE INDEX idx_order_item_product ON order_item(product_id);

CREATE TABLE payment (
    payment_id BIGSERIAL PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    payment_method VARCHAR(30) NOT NULL CHECK (
        payment_method IN ('card', 'paypal', 'apple_pay', 'affirm', 'gift_card')
    ),
    payment_provider VARCHAR(30) NOT NULL,
    card_network VARCHAR(20),
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    paid_at TIMESTAMP,
    payment_status VARCHAR(20) NOT NULL CHECK (payment_status IN ('pending', 'captured', 'refunded', 'failed'))
);
CREATE INDEX idx_payment_order ON payment(order_id);
CREATE INDEX idx_payment_status ON payment(payment_status);

CREATE TABLE shipment (
    shipment_id BIGSERIAL PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    warehouse_id INT NOT NULL REFERENCES warehouse(warehouse_id),
    carrier VARCHAR(20) NOT NULL CHECK (carrier IN ('UPS', 'FedEx', 'USPS')),
    service_level VARCHAR(20) NOT NULL CHECK (service_level IN ('ground', 'two_day', 'overnight')),
    tracking_number VARCHAR(40) UNIQUE,
    shipped_at TIMESTAMP,
    delivered_at TIMESTAMP,
    shipping_cost NUMERIC(10, 2) NOT NULL DEFAULT 0 CHECK (shipping_cost >= 0),
    shipping_status VARCHAR(20) NOT NULL CHECK (
        shipping_status IN ('label_created', 'in_transit', 'delivered', 'exception', 'returned')
    )
);
CREATE INDEX idx_shipment_order ON shipment(order_id);
CREATE INDEX idx_shipment_status ON shipment(shipping_status);

-- 6) Post-purchase feedback and returns
CREATE TABLE product_review (
    review_id BIGSERIAL PRIMARY KEY,
    order_item_id BIGINT NOT NULL UNIQUE REFERENCES order_item(order_item_id) ON DELETE CASCADE,
    rating INT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    review_title VARCHAR(120),
    review_text TEXT,
    helpful_votes INT NOT NULL DEFAULT 0 CHECK (helpful_votes >= 0),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_product_review_rating ON product_review(rating);

CREATE TABLE return_request (
    return_id BIGSERIAL PRIMARY KEY,
    order_item_id BIGINT NOT NULL REFERENCES order_item(order_item_id) ON DELETE CASCADE,
    return_reason VARCHAR(80) NOT NULL,
    return_status VARCHAR(20) NOT NULL CHECK (
        return_status IN ('requested', 'approved', 'received', 'refunded', 'rejected')
    ),
    requested_at TIMESTAMP NOT NULL,
    approved_at TIMESTAMP,
    refunded_amount NUMERIC(10, 2) NOT NULL DEFAULT 0 CHECK (refunded_amount >= 0)
);
CREATE INDEX idx_return_request_status ON return_request(return_status);
