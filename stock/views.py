import json
import os
import cloudinary.uploader
import razorpay
from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from .forms import RegisterForm, UserUpdateForm
from django.db.models import F, ExpressionWrapper, DecimalField
from .models import Stock, Portfolio, Transaction, User, Watchlist, Payment
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .utils import fetch_and_load_stock_data, fetch_live_prices
from .forecasting import generate_forecast
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth import login as auth_login
from decimal import Decimal

razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
FUND_AMOUNTS = [Decimal('500'), Decimal('1000'), Decimal('2000'), Decimal('5000')]


@login_required(login_url='/login/')
def profile(request):
    user = get_object_or_404(User, email=request.user.email)
    portfolio = get_object_or_404(Portfolio, user=user)

    if request.method == 'POST':
        if 'image' in request.FILES:
            try:
                if os.environ.get('CLOUDINARY_URL'):
                    result = cloudinary.uploader.upload(request.FILES['image'])
                    user.image = result['secure_url']
                user.save()
                return redirect('profile')
            except Exception as e:
                print(f"IMAGE UPLOAD ERROR: {e}", flush=True)
                return HttpResponse(f"Upload failed: {e}", status=500)
        form = UserUpdateForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            form.save()
            return redirect('profile')

    else:
        form = UserUpdateForm(instance=user)

    context = {
        'user': user,
        'portfolio': portfolio,
        'form': form,
    }
    return render(request, 'stock/profile.html', context)


@login_required(login_url='/login/')
def watchlist(request):
    user = request.user
    watchlist_items = Watchlist.objects.filter(user=user).select_related('stock')

    return render(request, 'stock/watchlist.html', {'watchlist_items': watchlist_items})


def stocks(request):
    stocks = Stock.objects.all()  # Fetch all stocks from the database
    return render(request, 'stock/stocks.html', {'stocks': stocks})

@login_required(login_url='/login/')
def portfolio(request):
    user = get_object_or_404(User, email=request.user.email)
    portfolio = get_object_or_404(Portfolio, user=user)
    transactions = Transaction.objects.filter(portfolio=portfolio)

    # Build per-stock holdings from active buy transactions
    holdings = {}
    for tx in transactions.filter(transaction_type='buy').select_related('stock'):
        sym = tx.stock.symbol
        if sym not in holdings:
            holdings[sym] = {
                'name': tx.stock.name,
                'symbol': sym,
                'quantity': 0,
                'total_invested': 0,
                'current_price': float(tx.stock.current_price),
            }
        holdings[sym]['quantity'] += tx.quantity
        holdings[sym]['total_invested'] += float(tx.price_per_share * tx.quantity)

    for h in holdings.values():
        h['current_value'] = round(h['current_price'] * h['quantity'], 2)
        h['profit_loss'] = round(h['current_value'] - h['total_invested'], 2)
        h['profit_loss_pct'] = round(
            (h['profit_loss'] / h['total_invested'] * 100) if h['total_invested'] > 0 else 0, 2
        )
        h['total_invested'] = round(h['total_invested'], 2)

    holdings_list = list(holdings.values())
    total_invested = round(sum(h['total_invested'] for h in holdings_list), 2)
    current_value = round(sum(h['current_value'] for h in holdings_list), 2)
    total_pnl = round(current_value - total_invested, 2)
    total_pnl_pct = round((total_pnl / total_invested * 100) if total_invested > 0 else 0, 2)

    context = {
        'user': user,
        'portfolio': portfolio,
        'transactions': transactions,
        'holdings': holdings_list,
        'holdings_json': json.dumps(holdings_list),
        'total_invested': total_invested,
        'current_value': current_value,
        'total_pnl': total_pnl,
        'total_pnl_pct': total_pnl_pct,
    }
    return render(request, 'stock/portfolio.html', context)

@login_required(login_url='/login/')
def transactions(request):
    transactions = Transaction.objects.filter(portfolio__user=request.user).select_related('stock')
    context = {
        'transactions': transactions
    }
    return render(request, 'stock/transactions.html', context)


def user_logout(request):
    logout(request)
    return redirect('login')



@csrf_exempt
def reload_stocks(request):
    if request.method == 'POST':
        fetch_and_load_stock_data()
        return JsonResponse({'status': 'Stocks reloaded successfully'})
    return JsonResponse({'error': 'Invalid request method'}, status=400)


@csrf_exempt
def refresh_live_prices(request):
    if request.method == 'POST':
        result = fetch_live_prices()
        return JsonResponse({
            'status': f"Updated {len(result['updated'])} stocks with live prices.",
            'updated': result['updated'],
            'failed': result['failed'],
        })
    return JsonResponse({'error': 'Invalid request method'}, status=400)


@login_required(login_url='/login/')
def home(request):
    user = request.user

    portfolio = Portfolio.objects.filter(user=user).first()  # Ensure to get the portfolio for the current user

    if portfolio:
        transactions = Transaction.objects.filter(
            portfolio=portfolio,
            transaction_type='buy'
        ).select_related('stock')

        transactions = transactions.annotate(
            current_price=F('stock__current_price'),
            total_dividend=ExpressionWrapper(
                F('stock__dividend__dividend_amount') * F('quantity'),
                output_field=DecimalField()
            ),
            profit_loss_possible=ExpressionWrapper(
                (F('stock__dividend__dividend_amount') + F('stock__current_price') - F('price_per_share')) * F('quantity'),
                output_field=DecimalField()
            )
        )
    else:
        transactions = None

    return render(request, 'stock/home.html', {'transactions': transactions})

def login(request):
    if request.method == 'POST':
        
        
        username = request.POST.get('username')
        password = request.POST.get('password')

        if (User.objects.filter(username=username).exists()) == False:
            messages.error(request, "Invalid Username")
            return render(request, 'stock/login.html')
        user = User.objects.get(username=username)

        if user.check_password(password):
            auth_login(request, user)
            return redirect(home)  # Redirect to the home page after successful login
        else:
            messages.error(request, "Invalid password.")
        
    else:
        form = AuthenticationForm()
    
    return render(request, 'stock/login.html')

def register(request):
    if request.method == 'POST':
        first_name = request.POST.get('first-name')
        last_name = request.POST.get('last-name')
        username = request.POST.get('username')
        password = request.POST.get('password')
        password_confirm = request.POST.get('password-confirm')
        phone = request.POST.get('phone')
        email = request.POST.get('email')

        # Check if passwords match
        if password != password_confirm:
            messages.error(request, "Passwords do not match.")
            return render(request, 'stock/register.html')

        # Check if username or email already exists
        if User.objects.filter(username=username).exists():
            messages.error(request, "Username is already taken.")
            return render(request, 'stock/register.html')

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email is already registered.")
            return render(request, 'stock/register.html')

        # Create the new user (create_user() hashes the password before saving)
        new_user = User.objects.create_user(
            email=email,
            username=username,
            password=password,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
        )
        new_portfolio = Portfolio(
            user = new_user

        )
        new_portfolio.save()

        messages.success(request, "Registration successful! You can now log in.")
        return redirect('login')  # Redirect to login page after successful registration

    return render(request, 'stock/register.html')



# Purchase Stock View
@login_required(login_url='/login/')
@csrf_exempt
def purchase_stock(request):
    if request.method == 'POST':
        stock_id = request.POST.get('stock_id')
        quantity = int(request.POST.get('quantity'))

        stock = get_object_or_404(Stock, id=stock_id)
        portfolio = get_object_or_404(Portfolio, user=request.user)

        if quantity > stock.quantity:
            return JsonResponse({'status': 'Not enough stock available to complete the purchase.'}, status=400)

        total_price = Decimal(quantity) * stock.current_price

        if total_price > portfolio.user.budget:
            return JsonResponse({'status': 'Not enough budget to complete the purchase.'}, status=400)

        stock.quantity -= quantity
        stock.save()

        portfolio.user.budget -= total_price
        portfolio.user.save()

        Transaction.objects.create(
            portfolio=portfolio,
            stock=stock,
            transaction_type='buy',
            quantity=quantity,
            price_per_share=stock.current_price
        )

        return JsonResponse({'status': 'Stock purchased successfully!'})

    return JsonResponse({'status': 'Invalid request'}, status=400)

# Add to Watchlist View
@login_required(login_url='/login/')
@csrf_exempt
def add_to_watchlist(request):
    if request.method == 'POST':
        stock_id = request.POST.get('stock_id')
        stock = get_object_or_404(Stock, id=stock_id)

        # Check if the stock is already in the user's watchlist
        if Watchlist.objects.filter(user=request.user, stock=stock).exists():
            return JsonResponse({'status': 'Stock is already in your watchlist.'}, status=400)

        # Add stock to watchlist
        watchlist_item = Watchlist.objects.create(user=request.user, stock=stock)
        return JsonResponse({'status': 'Stock added to watchlist!'})

    return JsonResponse({'status': 'Invalid request'}, status=400)

@login_required(login_url='/login/')
@csrf_exempt
def remove_from_watchlist(request):
    if request.method == 'POST':
        stock_id = request.POST.get('stock_id')
        stock = get_object_or_404(Stock, id=stock_id)  # Ensure the stock exists

        try:
            watchlist_item = Watchlist.objects.get(user=request.user, stock=stock)
            watchlist_item.delete()  # Remove the stock from the watchlist
            return JsonResponse({'status': f'{stock.name} removed from your watchlist.'})
        except Watchlist.DoesNotExist:
            return JsonResponse({'status': f'{stock.name} is not in your watchlist.'})

    return JsonResponse({'status': 'Invalid request.'})



@login_required(login_url='/login/')
def forecast(request, stock_id):
    stock = get_object_or_404(Stock, id=stock_id)
    result = generate_forecast(stock.symbol)

    context = {
        'stock': stock,
        'error': result.get('error'),
        'historical_json': json.dumps(result.get('historical', [])),
        'forecast_json': json.dumps(result.get('forecast', [])),
    }
    return render(request, 'stock/forecast.html', context)


@login_required(login_url='/login/')
def add_funds(request):
    context = {
        'amounts': FUND_AMOUNTS,
        'razorpay_key_id': settings.RAZORPAY_KEY_ID,
    }
    return render(request, 'stock/add_funds.html', context)


@login_required(login_url='/login/')
def create_order(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request'}, status=400)

    try:
        amount = Decimal(request.POST.get('amount', '0'))
    except Exception:
        return JsonResponse({'error': 'Invalid amount.'}, status=400)

    if amount <= 0:
        return JsonResponse({'error': 'Invalid amount.'}, status=400)

    order = razorpay_client.order.create({
        'amount': int(amount * 100),  # paise
        'currency': 'INR',
        'payment_capture': 1,
    })

    Payment.objects.create(user=request.user, amount=amount, razorpay_order_id=order['id'])

    return JsonResponse({
        'order_id': order['id'],
        'amount': order['amount'],
        'currency': order['currency'],
        'key_id': settings.RAZORPAY_KEY_ID,
    })


@login_required(login_url='/login/')
def verify_payment(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request'}, status=400)

    order_id = request.POST.get('razorpay_order_id')
    payment_id = request.POST.get('razorpay_payment_id')
    signature = request.POST.get('razorpay_signature')

    payment = get_object_or_404(Payment, razorpay_order_id=order_id, user=request.user)

    try:
        razorpay_client.utility.verify_payment_signature({
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature,
        })
    except razorpay.errors.SignatureVerificationError:
        return JsonResponse({'error': 'Payment verification failed.'}, status=400)

    if not payment.success:
        payment.success = True
        payment.razorpay_payment_id = payment_id
        payment.save()
        request.user.budget += payment.amount
        request.user.save()

    return JsonResponse({'status': 'ok'})


@login_required(login_url='/login/')
def payment_success(request):
    order_id = request.GET.get('order_id')
    payment = get_object_or_404(Payment, razorpay_order_id=order_id, user=request.user)
    return render(request, 'stock/payment_success.html', {'payment': payment})


@login_required(login_url='/login/')
def sell_stock(request, transaction_id):
    transaction = get_object_or_404(Transaction, id=transaction_id, portfolio__user=request.user)

    if transaction.transaction_type != 'buy' or transaction.quantity == 0:
        messages.error(request, 'No stocks to sell.')
        return redirect('home')

    if request.method != 'POST':
        return redirect('home')

    try:
        sell_qty = int(request.POST.get('quantity', 0))
    except (ValueError, TypeError):
        messages.error(request, 'Invalid quantity.')
        return redirect('home')

    if sell_qty <= 0 or sell_qty > transaction.quantity:
        messages.error(request, f'Quantity must be between 1 and {transaction.quantity}.')
        return redirect('home')

    stock = transaction.stock
    total_amount = Decimal(sell_qty) * stock.current_price

    user = request.user
    user.budget += total_amount
    user.save()

    stock.quantity += sell_qty
    stock.save()

    Transaction.objects.create(
        portfolio=transaction.portfolio,
        stock=stock,
        transaction_type='sell',
        quantity=sell_qty,
        price_per_share=stock.current_price,
    )

    if sell_qty == transaction.quantity:
        transaction.transaction_type = 'bs'
        transaction.save()
    else:
        transaction.quantity -= sell_qty
        transaction.save()

    return redirect(f'/?sold=True&amount={total_amount:.2f}')
