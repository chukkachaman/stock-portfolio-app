from django.contrib import admin
from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login, name='login'),
    path('register/', views.register, name='register'),
    path('profile/', views.profile, name='profile'),
    path('watchlist/', views.watchlist, name='watchlist'),
    path('stocks/', views.stocks, name='stocks'),
    path('portfolio/', views.portfolio, name='portfolio'),
    path('transactions/', views.transactions, name='transactions'),
    path('reload-stocks/', views.reload_stocks, name='reload_stocks'),
    path('logout/', views.user_logout, name='logout'),
    path('purchase_stock/', views.purchase_stock, name='purchase_stock'),
    path('add_to_watchlist/', views.add_to_watchlist, name='add_to_watchlist'),
    path('remove_from_watchlist/', views.remove_from_watchlist, name='remove_from_watchlist'),
    path('sell/<int:transaction_id>/', views.sell_stock, name='sell-stock'),
    

]
