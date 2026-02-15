import razorpay, json, os, requests, urllib3
from django.shortcuts import render, get_object_or_404, redirect
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from pathlib import Path
from dotenv import load_dotenv
from django.contrib.admin.views.decorators import staff_member_required
from .utils import send_twilio_message 
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from .models import Product, Order, OrderItem, Coupon, UserActivity, ContactMessage
from .filters import ProductFilter
from django.db.models import Q
import urllib.parse

# Initializations
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# This points to the folder containing manage.py
BASE_DIR = Path(__file__).resolve().parent.parent

# Use the / operator (pathlib magic) to join paths - No underline!
env_path = BASE_DIR / '.env'

# Load it
load_dotenv(dotenv_path=env_path)

# Debug prints
print(f"Checking path: {env_path}")
print(f"API Key Found: {'Yes' if os.getenv('GEMINI_API_KEY') else 'No'}")

client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

# --- 1. AI & GENERATION FUNCTIONS ---
@csrf_exempt
@staff_member_required
def generate_ai_description(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            p_name = data.get('name')
            
            # 1. Use os.getenv for security
            api_key = os.getenv("GEMINI_API_KEY") 
            if not api_key:
                return JsonResponse({'error': 'API Key missing in .env file'}, status=500)

            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={api_key}"
            payload = {"contents": [{"parts": [{"text": f"Write a professional 50-word description for {p_name}"}]}]}
            
            # 2. Set verify=True (False is a security risk)
            response = requests.post(url, json=payload, verify=True, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                text = result['candidates'][0]['content']['parts'][0]['text']
                return JsonResponse({'description': text})
            else:
                # 3. Enhanced Debugging: Return the actual error message from Google
                error_detail = response.json().get('error', {}).get('message', 'Unknown Google API Error')
                return JsonResponse({'error': f'Google API says: {error_detail}'}, status=response.status_code)

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid Method'}, status=400)

# --- 2. SHOP & SEARCH ---


def index(request):
    product_list = Product.objects.all().order_by('-id')
    query = request.GET.get('q')
    if query:
        product_list = product_list.filter(
            Q(name__icontains=query) | 
            Q(description__icontains=query) |
            Q(category__icontains=query)
        )

    # 3. Apply the Dropdown Filters (django-filter)
    # We pass request.GET to the filterset
    product_filter = ProductFilter(request.GET, queryset=product_list)
    
    # 4. Get the Cart from session (for the navbar badge)
    cart = request.session.get('cart', {})
    cart_total_items = sum(cart.values())

    context = {
        'filter': product_filter,       # This generates the form in your dropdown
        'products': product_filter.qs,  # This is the filtered list of products
        'query': query,
        'cart': cart,
        'cart_total_items': cart_total_items,
    }
    
    return render(request, 'index.html', context)

# --- 3. CART SYSTEM ---
def add_to_cart(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    cart = request.session.get('cart', {})
    p_id = str(product_id)
    current_qty = cart.get(p_id, 0)

    if product.stock <= 0:
        messages.error(request, f"Sorry, {product.name} is out of stock!")
    elif current_qty + 1 > product.stock:
        messages.warning(request, f"Only {product.stock} units available.")
    else:
        cart[p_id] = current_qty + 1
        request.session['cart'] = cart
        messages.success(request, f"{product.name} added to cart!")
    return redirect(request.META.get('HTTP_REFERER', 'index'))

def cart_view(request):
    cart = request.session.get('cart', {})
    cart_items = []
    base_total = 0

    for product_id, quantity in cart.items():
        try:
            product = Product.objects.get(id=product_id)
            subtotal = product.price * quantity
            base_total += subtotal
            cart_items.append({'product': product, 'quantity': quantity, 'subtotal': subtotal})
        except Product.DoesNotExist:
            continue

    # Discount Logic
    discount_amount = 0
    applied_coupon = None
    coupon_id = request.session.get('coupon_id')

    if coupon_id:
        try:
            applied_coupon = Coupon.objects.get(id=coupon_id, active=True, valid_to__gte=timezone.now())
            discount_amount = (base_total * applied_coupon.discount_percent) / 100
        except Coupon.DoesNotExist:
            request.session['coupon_id'] = None

    context = {
        'cart_items': cart_items,
        'base_total': base_total,
        'discount_amount': discount_amount,
        'total_price': max(0, base_total - discount_amount), # Ensure total isn't negative
        'applied_coupon': applied_coupon,
    }
    return render(request, 'cart.html', context)

# --- 4. CHECKOUT & PAYMENTS ---
def checkout_view(request):
    cart = request.session.get('cart', {})
    if not cart:
        messages.error(request, "Your cart is empty!")
        return redirect('index')

    # FIX: Only allow POST requests to capture data
    if request.method != "POST":
        return redirect('checkout_details')

    cust_name = request.POST.get('full_name')
    cust_email = request.POST.get('email')
    cust_phone = request.POST.get('phone')
    # Capture the new fields
    address = request.POST.get('address')
    state = request.POST.get('state')
    pincode = request.POST.get('pincode')

    # FIX: Ensure user actually filled the form
    if not cust_name or not cust_email or not cust_phone:
        messages.error(request, "Please fill in all contact details.")
        return redirect('checkout_details')

    products_in_cart = []
    total_amount = 0
    
    for p_id, qty in cart.items():
        product = get_object_or_404(Product, id=p_id)
        subtotal = product.price * qty
        total_amount += subtotal
        products_in_cart.append({'product': product, 'quantity': qty, 'subtotal': subtotal})

    # Discount logic
    discount_amount = 0
    applied_coupon = None
    coupon_id = request.session.get('coupon_id')

    if coupon_id:
        try:
            applied_coupon = Coupon.objects.get(id=coupon_id, active=True, valid_to__gte=timezone.now())
            discount_amount = (total_amount * applied_coupon.discount_percent) / 100
            total_amount -= discount_amount
        except Coupon.DoesNotExist:
            request.session['coupon_id'] = None

    razorpay_amount = int(total_amount * 100) 
    
    try:
        razor_order = client.order.create({
            "amount": razorpay_amount,
            "currency": "INR",
            "payment_capture": "1"
        })
        
        # --- 2. SAVE DATA TO THE ORDER MODEL ---
        # By saving 'email' and 'phone_number' here, your send_status_notification
        # and send_whatsapp_update functions will have the correct data to use.
        order = Order.objects.create(
            user=request.user if request.user.is_authenticated else None,
            full_name=cust_name,      # Added for personalized messages
            email=cust_email,          # Added for Email notifications
            phone_number=cust_phone,   # Added for WhatsApp notifications
            amount=total_amount,
            order_id=razor_order['id'],
            paid=False,
            coupon=applied_coupon,
            address=address, # Make sure these field names match your models.py
            state=state,
            pincode=pincode,
            status='Pending'
        )
        
        for item in products_in_cart:
            OrderItem.objects.create(
                order=order,
                product=item['product'],
                price=item['product'].price,
                quantity=item['quantity']
            )

        # --- 3. PASS TO SUMMARY PAGE ---
        context = {
            'products': products_in_cart,
            'total_amount': total_amount,
            'order_id': razor_order['id'],
            'razorpay_key': settings.RAZORPAY_KEY_ID,
            'cust_name': cust_name,
            'cust_email': cust_email,
            'cust_phone': cust_phone,
        }
        return render(request, 'checkout_summary.html', context)

    except Exception as e:
        return render(request, 'failure.html', {'error': f"Payment Initialization Error: {str(e)}"})



@csrf_exempt
def payment_success(request):
    if request.method == "POST":
        
        payment_id = request.POST.get('razorpay_payment_id')
        razorpay_order_id = request.POST.get('razorpay_order_id')
        signature = request.POST.get('razorpay_signature')

        try:
            # 1. Verify Payment Signature
            params_dict = {
                'razorpay_order_id': razorpay_order_id, 
                'razorpay_payment_id': payment_id, 
                'razorpay_signature': signature
            }
            client.utility.verify_payment_signature(params_dict)

            # 2. Update Order - Ensure order_id field stores the RAZORPAY ID
            order = Order.objects.get(order_id=razorpay_order_id)
            order.paid = True
            order.payment_id = payment_id
            order.status = 'Confirmed'
            order.save()

            # 3. Update Stock & Activity
            # Using orderitem_set to ensure we find the products
            for item in order.items.all():
                product = item.product
                product.stock -= item.quantity
                product.save()
                
                if order.user:
                    UserActivity.objects.get_or_create(
                        user=order.user, 
                        product=product, 
                        defaults={'score': 5}
                    )

            # --- Notifications ---
            whatsapp_msg = f"Hi {order.full_name}, your payment for Order #{order.order_id} was successful! Status: Confirmed. 🛍️"
            send_twilio_message(order.phone_number, whatsapp_msg)
            order.send_order_notification("Confirmed") 

            # 4. Clear Session
            request.session['cart'] = {}
            request.session['coupon_id'] = None
            
            return render(request, 'success.html', {'order': order})

        except Exception as e:
            print(f"PAYMENT VERIFICATION FAILED: {e}") # Check terminal for the real error
            return render(request, 'failure.html', {'error': str(e)})
            
    return redirect('index')

# --- 5. UTILITIES ---
def apply_coupon(request):
    if request.method == "POST":
        code = request.POST.get('coupon_code')
        now = timezone.now()
        try:
            coupon = Coupon.objects.get(code__iexact=code, active=True, 
                                      valid_from__lte=now, valid_to__gte=now)
            request.session['coupon_id'] = coupon.id
            messages.success(request, f"Coupon applied! {coupon.discount_percent}% off.")
        except Coupon.DoesNotExist:
            request.session['coupon_id'] = None
            messages.error(request, "Invalid or expired coupon.")
    return redirect('cart_view')



def about_view(request):
    """
    Renders the About Us page. 
    You can also pass dynamic data like total products sold.
    """
    context = {
        'total_products': Product.objects.count(),
        'store_name': "Shop Cart AI",
        'established_year': 2024
    }
    return render(request, 'about.html', context)

def contact_us(request):
    """
    The main contact view handling both the page display and form submission.
    """
    if request.method == "POST":
        name = request.POST.get('name')
        email = request.POST.get('email')
        subject = request.POST.get('subject', 'General Inquiry') # Optional field
        message_body = request.POST.get('message')

        # Basic Validation
        if not name or not email or not message_body:
            messages.error(request, "Bhai, saari fields bharna zaroori hai! (Please fill all fields)")
            return render(request, 'contact.html')

        try:
            # 1. Save to Database
            ContactMessage.objects.create(
                name=name, 
                email=email, 
                message=message_body
            )
            
            # 2. Optional: Send Email Notification to Admin
            # send_mail(
            #     f'New Contact Form: {subject}',
            #     f'From: {name} ({email})\n\nMessage: {message_body}',
            #     settings.DEFAULT_FROM_EMAIL,
            #     [settings.ADMIN_EMAIL],
            #     fail_silently=True,
            # )

            messages.success(request, "We have got your message! we will contact you soon.")
            return redirect('index') 
            
        except Exception as e:
            messages.error(request, f"something went wrong . Please try again later. Error: {e}")
            return redirect('contact_us')

    # If GET request, just show the page
    return render(request, 'contact.html')

def update_cart(request, product_id, action):
    """
    Handles incrementing, decrementing, or removing items from the session cart.
    """
    cart = request.session.get('cart', {})
    p_id = str(product_id)
    product = get_object_or_404(Product, id=product_id)

    if p_id in cart:
        if action == 'add':
            # Security Check: Compare requested quantity with actual stock
            if cart[p_id] < product.stock:
                cart[p_id] += 1
                messages.success(request, f"Updated quantity for {product.name}.")
            else:
                messages.warning(request, f"Sorry, only {product.stock} units in stock.")
        
        elif action == 'remove':
            cart[p_id] -= 1
            # If quantity hits 0, remove the item entirely
            if cart[p_id] <= 0:
                del cart[p_id]
                messages.info(request, f"{product.name} removed from cart.")
        
        elif action == 'delete':
            # Immediate removal regardless of quantity
            del cart[p_id]
            messages.info(request, f"{product.name} removed from cart.")

    request.session['cart'] = cart
    request.session.modified = True # Ensure Django saves the session
    return redirect('cart_view')

def signup_view(request):
    """
    Handles new user registration using Django's built-in UserCreationForm.
    """
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            # 1. Save the new user to the database
            user = form.save()
            
            # 2. Log the user in automatically after signup
            login(request, user)
            
            # 3. Show a friendly success message
            messages.success(request, f"Welcome to Shop Cart, {user.username}! Your account was created successfully. 🚀")
            
            # 4. Redirect to home page or a specific 'welcome' page
            return redirect('index')
        else:
            # If form is invalid (e.g., password too short), show errors
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field.capitalize()}: {error}")
    else:
        # If GET request, show a blank signup form
        form = UserCreationForm()
        
    return render(request, 'signup.html', {'form': form})

def login_view(request):
    """
    Handles user authentication.
    """
    if request.user.is_authenticated:
        return redirect('index')

    if request.method == "POST":
        u = request.POST.get('username')
        p = request.POST.get('password')
        
        # 1. Authenticate credentials
        user = authenticate(username=u, password=p)
        
        if user is not None:
            # 2. Start the session
            login(request, user)
            
            # 3. Handle 'next' parameter (Redirect user back to where they were)
            next_url = request.GET.get('next')
            messages.success(request, f"Welcome back, {user.username}! 🎉")
            
            if next_url:
                return redirect(next_url)
            return redirect('index')
        else:
            # 4. Invalid credentials
            messages.error(request, "Invalid username or password. Please try again.")
            return render(request, 'login.html') # Keep them on the login page

    # If GET request, show login page
    return render(request, 'login.html')

def logout_view(request):
    """
    Clears the user's session and redirects to the home page.
    """
    # 1. Standard Django logout (removes the user ID from the session)
    logout(request)
    
    # 2. Optional: Clear the cart upon logout 
    # (Do this if you want a fresh cart for every login session)
    if 'cart' in request.session:
        del request.session['cart']
    
    # 3. Success Message
    messages.info(request, "you are logged out!")
    
    # 4. Redirect to home
    return redirect('index')

@login_required
def profile_view(request):
    """
    Displays the user's order history and activity.
    """
    # 1. Fetch only orders belonging to this user
    # We use .filter(paid=True) so the user doesn't see failed/abandoned attempts
    orders = Order.objects.filter(user=request.user, paid=True).order_by('-id')
    
    # 2. Fetch recent activity (helpful for showing 'Recently Viewed' or 'Bought')
    recent_activity = UserActivity.objects.filter(user=request.user).order_by('-id')[:5]

    context = {
        'user': request.user,
        'orders': orders,
        'recent_activity': recent_activity,
        'order_count': orders.count(),
    }
    
    return render(request, 'profile.html', context)

@staff_member_required
def add_product_view(request):
    """
    Allows staff/admins to add new products via a form.
    """
    if request.method == 'POST':
        # 1. Capture data from the POST request
        name = request.POST.get('name')
        category = request.POST.get('category')
        price = request.POST.get('price')
        stock = request.POST.get('stock')
        description = request.POST.get('description')
        
        # 2. Capture the uploaded image from request.FILES
        image = request.FILES.get('image')

        # 3. Simple validation check
        if name and price and stock:
            try:
                product = Product.objects.create(
                    name=name,
                    category=category,
                    price=price,
                    stock=stock,
                    description=description,
                    image=image
                )
                messages.success(request, f"Product '{product.name}' added successfully! 📦")
                return redirect('index')
            except Exception as e:
                messages.error(request, f"Error saving product: {e}")
        else:
            messages.error(request, "Please fill in all required fields (Name, Price, Stock).")

    # If GET request, show the product form
    return render(request, 'product_form.html')


@staff_member_required
def list_available_models(request):
    """
    Fetches and displays available Gemini models from Google.
    Restricted to staff for security.
    """
    api_key = os.getenv("GEMINI_API_KEY")  # Get key from .env
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    
    try:
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            # Return the list of models directly to the browser as JSON
            return JsonResponse(response.json(), safe=False)
        else:
            return JsonResponse({
                'error': 'Failed to fetch models', 
                'status_code': response.status_code,
                'details': response.text
            }, status=400)
            
    except requests.exceptions.RequestException as e:
        return JsonResponse({'error': f'Connection failed: {str(e)}'}, status=500)
    
from django.shortcuts import render, get_object_or_404
from .models import Order

def order_detail_view(request, order_id):
    """
    Displays the status and details of a specific order.
    Matches the URL path: track-order/<str:order_id>/
    """
    clean_id = urllib.parse.unquote(order_id)
    # 1. Fetch the order using the unique string ID (Razorpay ID)
    order = get_object_or_404(Order, order_id=order_id)
    
    # 2. Security Check (Optional but Recommended)
    # If the order belongs to a user, ensure only that user can see it
    if order.user and request.user != order.user:
        return render(request, '403.html', {'message': 'You do not have permission to view this order.'}, status=403)

    # 3. Context for the tracking page
    context = {
        'order': order,
        'items': order.items.all(), # Assumes related_name='items' in OrderItem model
        'status_steps': ['Pending', 'Confirmed', 'Shipped', 'Delivered'],
    }
    
    return render(request, 'order_tracking.html', context)

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import Order

@login_required
def my_orders(request):
    """
    Displays a list of all orders placed by the currently logged-in user.
    """
    # 1. Fetch orders linked to the user
    # We use .order_by('-created_at') to show newest orders first
    orders = Order.objects.filter(user=request.user).order_by('-id')
    
    # 2. Count total orders for display in the dashboard
    total_orders = orders.count()
    
    context = {
        'orders': orders,
        'total_orders': total_orders,
    }
    
    return render(request, 'my_orders.html', context)

from django.shortcuts import redirect
from django.contrib import messages
from .models import ContactMessage

def contact_view(request):
    """
    Handles the POST data from the contact form.
    URL Path: contact-submit/
    """
    if request.method == "POST":
        name = request.POST.get('name')
        email = request.POST.get('email')
        subject = request.POST.get('subject', 'No Subject')
        message_body = request.POST.get('message')

        # 1. Validation Logic
        if not name or not email or not message_body:
            messages.error(request, " Please fill all fields")
            # Redirect back to the contact page or index
            return redirect(request.META.get('HTTP_REFERER', 'index'))

        try:
            # 2. Save to Database
            ContactMessage.objects.create(
                name=name,
                email=email,
                message=message_body
            )
            
            # 3. Success Feedback
            messages.success(request, "we got your message,we will contact you soon.")
            
        except Exception as e:
            # Handle database errors gracefully
            messages.error(request, f"Server issue: {str(e)}")
            
        return redirect('index')

    # If someone tries to access /contact-submit/ via GET, send them home
    return redirect('index')


from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from twilio.twiml.messaging_response import MessagingResponse
from .models import Order  # Ensure this import matches your app structure

from google import genai
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from twilio.twiml.messaging_response import MessagingResponse
from .models import Order  # Ensure this matches your app structure

# 1. Configure the Brain (Gemini)


ai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

@csrf_exempt
def whatsapp_webhook(request):
    incoming_msg = request.POST.get('Body', '').strip()
    sender_phone_raw = request.POST.get('From', '')
    
    # Cleaning the phone number
    sender_phone = sender_phone_raw.replace('whatsapp:+91', '').replace('whatsapp:', '').strip()

    # 2. DATABASE LOOKUP
    user_orders = Order.objects.filter(phone_number__contains=sender_phone)
    
    if user_orders.exists():
        order_context = "USER ORDER HISTORY:\n"
        for o in user_orders:
            order_context += f"- ID: {o.order_id}, Status: {o.status}, Item: {o.product_brand}\n"
    else:
        order_context = "The user has no orders in our records."

    # 3. THE PROMPT
    prompt = f"""
    Context: {order_context}
    User asked: {incoming_msg}
    
    Instruction: Answer using the context above. If you don't find the ID they mention, tell them.
    Keep it friendly and short.
    """

    # 4. THE GENERATION (This is where your error was!)
    try:
        # We use 'client.models.generate_content' instead of just 'model'
        response = ai_client.models.generate_content(
            model="gemini-3-flash-preview", 
            contents=prompt
        )
        reply_text = response.text
    except Exception as e:
        import traceback
        print("---------- AI ERROR START ----------")
        print(traceback.format_exc())
        print("---------- AI ERROR END ----------")
        reply_text = "I'm having trouble thinking. Please try again later!"

    # 5. TWILIO DELIVERY
    twiml_resp = MessagingResponse()
    twiml_resp.message(reply_text)
    
    return HttpResponse(str(twiml_resp), content_type='application/xml')

def checkout_details_view(request):
    # This simply shows the HTML page with the input boxes
    return render(request, 'checkout_details.html')

from .utils import render_to_pdf # Assuming you have the helper in utils.py
from django.http import HttpResponse

def generate_pdf_view(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    data = {'order': order}
    pdf = render_to_pdf('invoice.html', data)
    if pdf:
        response = HttpResponse(pdf, content_type='application/pdf')
        filename = f"Invoice_{order.order_id}.pdf"
        content = f"inline; filename={filename}"
        response['Content-Disposition'] = content
        return response
    return HttpResponse("Not Found")



