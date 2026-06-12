#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py shell -c "
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute('DROP SCHEMA public CASCADE')
    cursor.execute('CREATE SCHEMA public')
    cursor.execute('GRANT ALL ON SCHEMA public TO public')
"
python manage.py migrate
python manage.py shell -c "from stock.utils import fetch_and_load_stock_data; fetch_and_load_stock_data()"
