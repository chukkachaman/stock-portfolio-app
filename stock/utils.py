import json
import os
from django.utils import timezone
from .models import Stock, Dividend

def fetch_and_load_stock_data():
    json_file_path = "./stock/stocks.json"

    try:
        # Open and load the local JSON file
        with open(json_file_path, 'r') as file:
            data = json.load(file)

        print("Data loaded successfully.")
        
        # Iterate through the stock data and update/create entries in the database
        for stock_data in data:
            print(f"Processing stock data: {stock_data}")  # Debug line

            symbol = stock_data.get('symbol')
            name = stock_data.get('name')
            market = stock_data.get('market')
            quantity = stock_data.get('quantity', 0)
            current_price = stock_data.get('current_price', 0)

            # Update or create stock in the database
            stock, created = Stock.objects.update_or_create(
                symbol=symbol,
                defaults={
                    'name': name,
                    'market': market,
                    'quantity': quantity,
                    'current_price': current_price,
                }
            )
            dividend, created = Dividend.objects.update_or_create(
                stock = stock,
            )
            if created:
                print(f"Created new stock entry: {symbol}")
            else:
                print(f"Updated stock entry: {symbol}")

    except FileNotFoundError:
        print(f"File {json_file_path} not found.")
    except json.JSONDecodeError:
        print("Error decoding JSON file.")
    except Exception as e:
        print(f"An error occurred: {e}")


