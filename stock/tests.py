from unittest.mock import patch

import numpy as np
import pandas as pd
from django.test import TestCase, Client
from django.urls import reverse

from .forecasting import generate_forecast
from .models import Portfolio, Stock, User


def _fake_history(days=90, start_price=100.0):
    dates = pd.date_range(end=pd.Timestamp.today(), periods=days, freq="D")
    prices = start_price + np.cumsum(np.random.default_rng(0).normal(0, 1, size=days))
    return pd.DataFrame({"Close": prices}, index=dates)


class ForecastingTests(TestCase):
    @patch("stock.forecasting.yf.Ticker")
    def test_generate_forecast_returns_historical_and_forecast_points(self, mock_ticker):
        mock_ticker.return_value.history.return_value = _fake_history()

        result = generate_forecast("FAKE", forecast_days=7)

        self.assertNotIn("error", result)
        self.assertEqual(result["symbol"], "FAKE")
        self.assertEqual(len(result["forecast"]), 7)
        self.assertTrue(len(result["historical"]) > 0)

    @patch("stock.forecasting.yf.Ticker")
    def test_generate_forecast_reports_error_on_insufficient_history(self, mock_ticker):
        mock_ticker.return_value.history.return_value = _fake_history(days=2)

        result = generate_forecast("FAKE")

        self.assertIn("error", result)


class ForecastViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="trader@example.com", username="trader", password="pw12345"
        )
        Portfolio.objects.create(user=self.user)
        self.stock = Stock.objects.create(symbol="FAKE", name="Fake Corp", market="NASDAQ")

    @patch("stock.forecasting.yf.Ticker")
    def test_forecast_view_renders_chart_data(self, mock_ticker):
        mock_ticker.return_value.history.return_value = _fake_history()
        self.client.force_login(self.user)

        response = self.client.get(reverse("forecast", args=[self.stock.id]))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "stock/forecast.html")
        self.assertContains(response, "FAKE")

    def test_forecast_view_requires_login(self):
        response = self.client.get(reverse("forecast", args=[self.stock.id]))
        self.assertEqual(response.status_code, 302)
