from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd
from django.test import TestCase, Client
from django.urls import reverse

from .forecasting import generate_forecast
from .models import Payment, Portfolio, Stock, User


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


class AuthTests(TestCase):
    def test_register_hashes_password_and_allows_login(self):
        response = self.client.post(reverse("register"), {
            "first-name": "Test",
            "last-name": "Trader",
            "username": "testtrader",
            "password": "correcthorsebattery",
            "password-confirm": "correcthorsebattery",
            "phone": "1234567890",
            "email": "testtrader@example.com",
        })
        self.assertEqual(response.status_code, 302)

        user = User.objects.get(username="testtrader")
        self.assertNotEqual(user.password, "correcthorsebattery")
        self.assertTrue(user.password.startswith("pbkdf2_") or "$" in user.password)

        login_ok = self.client.login(username="testtrader", password="wrongpassword")
        self.assertFalse(login_ok)

        response = self.client.post(reverse("login"), {
            "username": "testtrader",
            "password": "wrongpassword",
        })
        self.assertContains(response, "Invalid password")

        response = self.client.post(reverse("login"), {
            "username": "testtrader",
            "password": "correcthorsebattery",
        })
        self.assertEqual(response.status_code, 302)


class PaymentTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="trader@example.com", username="trader", password="pw12345"
        )
        self.user.refresh_from_db()
        Portfolio.objects.create(user=self.user)
        self.client.force_login(self.user)

    def test_add_funds_page_lists_amounts(self):
        response = self.client.get(reverse("add_funds"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "500")

    @patch("stock.views.stripe.checkout.Session.create")
    def test_create_checkout_session_redirects_to_stripe_and_records_pending_payment(self, mock_create):
        mock_create.return_value = SimpleNamespace(id="cs_test_123", url="https://checkout.stripe.com/pay/cs_test_123")

        response = self.client.post(reverse("create_checkout_session"), {"amount": "1000"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "https://checkout.stripe.com/pay/cs_test_123")

        payment = Payment.objects.get(stripe_session_id="cs_test_123")
        self.assertEqual(payment.user, self.user)
        self.assertEqual(payment.amount, Decimal("1000"))
        self.assertFalse(payment.success)

    def test_create_checkout_session_rejects_invalid_amount(self):
        response = self.client.post(reverse("create_checkout_session"), {"amount": "-5"})
        self.assertRedirects(response, reverse("add_funds"))
        self.assertEqual(Payment.objects.count(), 0)

    @patch("stock.views.stripe.checkout.Session.retrieve")
    def test_payment_success_credits_budget_once_when_paid(self, mock_retrieve):
        mock_retrieve.return_value = SimpleNamespace(payment_status="paid")
        payment = Payment.objects.create(user=self.user, amount=Decimal("1000"), stripe_session_id="cs_test_456")
        starting_budget = self.user.budget

        response = self.client.get(reverse("payment_success") + "?session_id=cs_test_456")
        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        payment.refresh_from_db()
        self.assertTrue(payment.success)
        self.assertEqual(self.user.budget, starting_budget + Decimal("1000"))

        # Visiting the success page again must not double-credit the budget.
        self.client.get(reverse("payment_success") + "?session_id=cs_test_456")
        self.user.refresh_from_db()
        self.assertEqual(self.user.budget, starting_budget + Decimal("1000"))
        mock_retrieve.assert_called_once()

    @patch("stock.views.stripe.checkout.Session.retrieve")
    def test_payment_success_does_not_credit_budget_when_unpaid(self, mock_retrieve):
        mock_retrieve.return_value = SimpleNamespace(payment_status="unpaid")
        Payment.objects.create(user=self.user, amount=Decimal("1000"), stripe_session_id="cs_test_789")
        starting_budget = self.user.budget

        self.client.get(reverse("payment_success") + "?session_id=cs_test_789")

        self.user.refresh_from_db()
        self.assertEqual(self.user.budget, starting_budget)
