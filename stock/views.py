from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from .forms import RegisterForm, UserUpdateForm
from django.contrib.auth.hashers import make_password
from django.db.models import F, ExpressionWrapper, DecimalField
from .models import Stock, Portfolio, Transaction, User, Watchlist
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .utils import fetch_and_load_stock_data  # Import your function
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth import login as auth_login
from decimal import Decimal


@login_required(login_url='/login/')
def profile(request):
    user = get_object_or_404(User, email=request.user.email)
    portfolio = get_object_or_404(Portfolio, user=user)

    if request.method == 'POST':
        if 'image' in request.FILES:
            user.image = request.FILES['image']
            user.save()
            return redirect('profile')
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
    
    total_profit_loss = portfolio.profit_loss  # Assuming you have a method to calculate this
    total_investment = sum(tx.price_per_share * tx.quantity for tx in transactions)  # Example for investment calculation

    context = {
        'user': user,
        'portfolio': portfolio,
        'transactions': transactions,
        'total_profit_loss': total_profit_loss,
        'total_investment': total_investment,
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
        print(username, password)

        if (User.objects.filter(username=username).exists()) == False:
            messages.error(request, "Invalid Username")
            return render(request, 'stock/login.html')
        user = User.objects.get(username=username)
        
        user_password = User.objects.get(username=username).password
        if user_password == password:
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

        # Create the new user
        new_user = User(
            email=email,
            username=username,
            password=password,  # The manager handles password hashing
            first_name=first_name,
            last_name=last_name,
            phone=phone,
        )
        new_user.save() 
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
def sell_stock(request, transaction_id):
    transaction = get_object_or_404(Transaction, id=transaction_id, portfolio__user=request.user)

    if transaction.transaction_type != 'buy' or transaction.quantity == 0:
        messages.error(request, 'No stocks to sell in this transaction.')
        return redirect('home')  # Assuming 'home' is the main page

    stock = transaction.stock

    total_amount_obtained = transaction.quantity * stock.current_price

    user = request.user
    user.budget += total_amount_obtained
    user.save()

    stock.quantity += transaction.quantity
    stock.save()
    new_transaction = Transaction(
        portfolio = transaction.portfolio,
        stock = transaction.stock,
        transaction_type = 'sell',
        quantity = transaction.quantity,
        price_per_share = stock.current_price,

    )
    transaction.transaction_type = 'bs'
    transaction.save()


    new_transaction.save()

    messages.success(request, f'Successfully sold stocks for Rs. {total_amount_obtained:.2f}.')

    return redirect(f'/?sold=True&amount={total_amount_obtained:.2f}')
