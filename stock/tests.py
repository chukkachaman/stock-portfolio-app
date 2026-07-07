from decimal import Decimal
from unittest.mock import patch

import numpy as np
import pandas as pd
import razorpay
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

    @patch("stock.views.razorpay_client.order.create")
    def test_create_order_records_pending_payment(self, mock_create):
        mock_create.return_value = {"id": "order_test_123", "amount": 100000, "currency": "INR"}

        response = self.client.post(reverse("create_order"), {"amount": "1000"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["order_id"], "order_test_123")

        payment = Payment.objects.get(razorpay_order_id="order_test_123")
        self.assertEqual(payment.user, self.user)
        self.assertEqual(payment.amount, Decimal("1000"))
        self.assertFalse(payment.success)

    def test_create_order_rejects_invalid_amount(self):
        response = self.client.post(reverse("create_order"), {"amount": "-5"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Payment.objects.count(), 0)

    @patch("stock.views.razorpay_client.utility.verify_payment_signature")
    def test_verify_payment_credits_budget_once_on_valid_signature(self, mock_verify):
        mock_verify.return_value = True
        payment = Payment.objects.create(user=self.user, amount=Decimal("1000"), razorpay_order_id="order_test_456")
        starting_budget = self.user.budget

        response = self.client.post(reverse("verify_payment"), {
            "razorpay_order_id": "order_test_456",
            "razorpay_payment_id": "pay_test_456",
            "razorpay_signature": "sig_test_456",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

        self.user.refresh_from_db()
        payment.refresh_from_db()
        self.assertTrue(payment.success)
        self.assertEqual(payment.razorpay_payment_id, "pay_test_456")
        self.assertEqual(self.user.budget, starting_budget + Decimal("1000"))

        # Calling verify again (e.g. a retried request) must not double-credit the budget.
        self.client.post(reverse("verify_payment"), {
            "razorpay_order_id": "order_test_456",
            "razorpay_payment_id": "pay_test_456",
            "razorpay_signature": "sig_test_456",
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.budget, starting_budget + Decimal("1000"))

    @patch("stock.views.razorpay_client.utility.verify_payment_signature")
    def test_verify_payment_rejects_bad_signature(self, mock_verify):
        mock_verify.side_effect = razorpay.errors.SignatureVerificationError("bad signature")
        Payment.objects.create(user=self.user, amount=Decimal("1000"), razorpay_order_id="order_test_789")
        starting_budget = self.user.budget

        response = self.client.post(reverse("verify_payment"), {
            "razorpay_order_id": "order_test_789",
            "razorpay_payment_id": "pay_test_789",
            "razorpay_signature": "tampered_signature",
        })
        self.assertEqual(response.status_code, 400)

        self.user.refresh_from_db()
        self.assertEqual(self.user.budget, starting_budget)
