import json
import os
import yfinance as yf
from django.utils import timezone
from .models import Stock, Dividend

def fetch_and_load_stock_data():
    json_file_path = "./stock/stocks.json"

    try:
        with open(json_file_path, 'r') as file:
            data = json.load(file)

        for stock_data in data:
            symbol = stock_data.get('symbol')
            name = stock_data.get('name')
            market = stock_data.get('market')
            quantity = stock_data.get('quantity', 0)
            current_price = stock_data.get('current_price', 0)

            stock, created = Stock.objects.update_or_create(
                symbol=symbol,
                defaults={
                    'name': name,
                    'market': market,
                    'quantity': quantity,
                    'current_price': current_price,
                }
            )
            Dividend.objects.update_or_create(stock=stock)

    except FileNotFoundError:
        print(f"File {json_file_path} not found.")
    except json.JSONDecodeError:
        print("Error decoding JSON file.")
    except Exception as e:
        print(f"An error occurred: {e}")


def fetch_live_prices():
    """Fetch real-time prices from Yahoo Finance and update the database."""
    stocks = Stock.objects.all()
    updated = []
    failed = []

    for stock in stocks:
        try:
            ticker = yf.Ticker(stock.symbol)
            info = ticker.fast_info
            live_price = round(info.last_price, 2)

            if live_price and live_price > 0:
                stock.current_price = live_price
                stock.save()
                updated.append(stock.symbol)
            else:
                failed.append(stock.symbol)
        except Exception as e:
            print(f"Failed to fetch price for {stock.symbol}: {e}")
            failed.append(stock.symbol)

    return {'updated': updated, 'failed': failed}


