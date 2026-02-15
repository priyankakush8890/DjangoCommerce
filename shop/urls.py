

from django.urls import path
from . import views

urlpatterns = [
    # --- 1. Main Pages ---
    path('', views.index, name='index'),
    path('about/', views.about_view, name='about'),
    path('contact/', views.contact_us, name='contact_us'),
    
    
    # --- 2. Cart System ---
    path('cart/', views.cart_view, name='cart_view'), 
    path('add-to-cart/<int:product_id>/', views.add_to_cart, name='add_to_cart'),
    path('update-cart/<int:product_id>/<str:action>/', views.update_cart, name='update_cart'),
    path('generate-pdf/<int:order_id>/', views.generate_pdf_view, name='generate_pdf'),
    
    # --- 3. Checkout & Payments ---
    path('checkout-details/', views.checkout_details_view, name='checkout_details'),
    path('process-checkout/', views.checkout_view, name='checkout_view'),
    path('payment-success/', views.payment_success, name='payment_success'),
    path('apply-coupon/', views.apply_coupon, name='apply_coupon'),
    
    
    # --- 4. User Authentication ---
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('my-orders/', views.my_orders, name='my_orders'),
    path('track-order/<str:order_id>/', views.order_detail_view, name='order_tracking'),
    
    # --- 5. AI & Admin Tools ---
    path('add-product/', views.add_product_view, name='add_product'),
    path('generate-ai-description/', views.generate_ai_description, name='ai_desc'),
    path('list-models/', views.list_available_models, name='list_models'),
    path('whatsapp-reply/', views.whatsapp_webhook, name='whatsapp_reply'),
    path('contact-submit/', views.contact_view, name='contact_submit'),
]