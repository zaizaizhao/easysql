# Product Demo Dataset (US Market)

This example provides an English-first e-commerce dataset for EasySQL demos.
It is designed for hackathon presentations where judges expect familiar US business
concepts (orders, shipping, returns, taxes, inventory, and customer segments).

## Files

- `00_init.sql` - Drops and recreates the `product` database.
- `01_schema.sql` - Creates tables and indexes.
- `02_test_data.sql` - Seeds realistic US-market sample data.
- `init_db.py` - One-command initializer for local PostgreSQL.
- `demo_questions_en.md` - Ready-to-use English demo prompts.

## Quick Setup

```bash
cd examples/product
python init_db.py
```

You can also run SQL files manually in this order:

1. `00_init.sql` (run from `postgres` DB)
2. `01_schema.sql` (run in `product` DB)
3. `02_test_data.sql` (run in `product` DB)

## Recommended `.env` Settings

```ini
DB_PRODUCT_TYPE=postgresql
DB_PRODUCT_HOST=localhost
DB_PRODUCT_PORT=5432
DB_PRODUCT_USER=postgres
DB_PRODUCT_PASSWORD=your_password
DB_PRODUCT_DATABASE=product

# Keep retrieval focused on this domain
CORE_TABLES=orders,order_item,product,customer,shipment,payment,inventory
```

Then refresh schema/vector indexes:

```bash
python main.py run
```
