# Stock Portfolio App

A full-stack stock trading simulation platform built with Django. Users get a **$5,000 virtual budget** to buy and sell real NASDAQ/NYSE stocks with live prices fetched from Yahoo Finance.

---

## Features

- **User Authentication** — Register, login, logout with custom email-based user model
- **Live Stock Prices** — Real-time prices from Yahoo Finance (AAPL, TSLA, NVDA, MSFT and 17 more)
- **Buy Stocks** — Purchase any quantity within your budget
- **Sell Stocks** — Sell any partial or full quantity of your holdings
- **Portfolio Dashboard** — Interactive charts (donut + bar) showing allocation and profit/loss
- **Price Forecast** — XGBoost-based short-term price prediction per stock, trained on trailing-window lag features from Yahoo Finance history
- **Watchlist** — Save stocks to track without buying
- **Transaction History** — Full log of all buys and sells
- **Profile Page** — Update your profile info and picture

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Django (Python) |
| Database | SQLite |
| Frontend | HTML, CSS, jQuery |
| Charts | Chart.js |
| Live Prices | yfinance (Yahoo Finance) |
| Forecasting | XGBoost, scikit-learn, Pandas, NumPy |
| Image Handling | Pillow |

---

## Getting Started

### Prerequisites
- Python 3.10+
- pip

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/chukkachaman/stock-portfolio-app.git
   cd stock-portfolio-app
   ```

2. **Install dependencies**
   ```bash
   pip install django yfinance pillow django-browser-reload
   ```

3. **Apply migrations**
   ```bash
   python manage.py migrate
   ```

4. **Load stock data**
   ```bash
   python -c "import django, os; os.environ['DJANGO_SETTINGS_MODULE']='stock_portfolio.settings'; django.setup(); from stock.utils import fetch_and_load_stock_data; fetch_and_load_stock_data()"
   ```

5. **Run the server**
   ```bash
   python manage.py runserver
   ```

6. **Open in browser**
   ```
   http://127.0.0.1:8000
   ```

---

## Usage

1. Register an account — you start with a **$5,000 budget**
2. Go to **Stocks** → click **Refresh Live Prices** to fetch current market prices
3. Enter a quantity and click **Purchase** to buy stocks
4. Go to **Home** to see your holdings — enter quantity and click **Sell** to sell
5. Go to **Portfolio** to see your allocation chart and profit/loss per stock
6. Add stocks to **Watchlist** to track them without buying

---

## Project Structure

```
stock-portfolio-app/
├── stock/                  # Main Django app
│   ├── models.py           # User, Stock, Portfolio, Transaction, Watchlist, Dividend
│   ├── views.py            # All view logic
│   ├── urls.py             # URL routing
│   ├── utils.py            # Live price fetching (yfinance)
│   ├── forecasting.py      # XGBoost price forecasting
│   └── migrations/
├── stock_portfolio/        # Django project config
│   ├── settings.py
│   └── urls.py
├── templates/stock/        # HTML templates
├── static/stock/           # CSS and images
└── manage.py
```

---

## Future Plans

- Auto price refresh every few minutes using Celery
- Stock price history charts with candlestick view
- Algorithmic trading module

---

## License

MIT License
