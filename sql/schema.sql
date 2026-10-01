-- Freight platform schema. Primary keys only here; foreign keys are added by
-- constraints.sql after the bulk load. No secondary indexes: that's the point.
DROP TABLE IF EXISTS invoices, tracking_events, consignments, carriers, customers CASCADE;

CREATE TABLE customers (
    customer_id  integer      PRIMARY KEY,
    name         text         NOT NULL,
    country      char(2)      NOT NULL,
    created_at   timestamptz  NOT NULL
);

CREATE TABLE carriers (
    carrier_id   integer      PRIMARY KEY,
    name         text         NOT NULL,
    mode         text         NOT NULL CHECK (mode IN ('road', 'air', 'sea', 'rail', 'courier'))
);

CREATE TABLE consignments (
    consignment_id   bigint         PRIMARY KEY,
    customer_id      integer        NOT NULL,
    carrier_id       integer        NOT NULL,
    -- Unique in practice, but deliberately no UNIQUE constraint yet:
    -- a UNIQUE constraint would silently create an index.
    tracking_number  text           NOT NULL,
    status           text           NOT NULL CHECK (status IN
                        ('created', 'picked_up', 'in_transit', 'out_for_delivery', 'delivered', 'exception')),
    created_at       timestamptz    NOT NULL,
    weight_kg        numeric(10,2)  NOT NULL CHECK (weight_kg > 0),
    price            numeric(12,2)  NOT NULL CHECK (price >= 0)
);

CREATE TABLE tracking_events (
    event_id         bigint       PRIMARY KEY,
    consignment_id   bigint       NOT NULL,
    status           text         NOT NULL,
    location         text         NOT NULL,
    occurred_at      timestamptz  NOT NULL
);

CREATE TABLE invoices (
    invoice_id       bigint         PRIMARY KEY,
    consignment_id   bigint         NOT NULL,
    customer_id      integer        NOT NULL,
    issued_at        timestamptz    NOT NULL,
    due_at           timestamptz    NOT NULL,
    amount           numeric(12,2)  NOT NULL,
    status           text           NOT NULL CHECK (status IN ('issued', 'paid', 'void'))
);
