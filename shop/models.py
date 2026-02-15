import os  # <--- Ye zaroori hai 'os.getenv' ke liye
from django.db import models
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from twilio.rest import Client  # <--- Ye zaroori hai WhatsApp ke liye
from datetime import timedelta


# --- 1. Product Table ---
class Product(models.Model):
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='products/') 
    stock = models.PositiveIntegerField(default=10)

    def __str__(self):
        return self.name

# --- 2. Coupon Table ---
class Coupon(models.Model):
    code = models.CharField(max_length=50, unique=True)
    discount_percent = models.PositiveIntegerField()
    active = models.BooleanField(default=True)
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()

    def __str__(self):
        return self.code

# --- 3. Order Table ---
class Order(models.Model):
    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Shipped', 'Shipped'),
        ('Delivered', 'Delivered'),
        ('Cancelled', 'Cancelled'),
        ('Packed', 'Packed'),
        ('On the Way', 'On the Way'),
        ('Confirmed', 'Confirmed'),

    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    amount = models.IntegerField()  
    order_id = models.CharField(max_length=100, blank=True) 
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Placed')
    updated_at = models.DateTimeField(auto_now=True)
    estimated_delivery = models.DateField(null=True, blank=True)
    payment_id = models.CharField(max_length=100, blank=True) 
    paid = models.BooleanField(default=False)
    full_name = models.CharField(max_length=200, null=True)
    email = models.EmailField(null=True)
    phone_number = models.CharField(max_length=15, null=True, blank=True)
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True)
    invoice_sent = models.BooleanField(default=False)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    address = models.TextField(null=True, blank=True)
    state = models.CharField(max_length=100, null=True, blank=True)
    pincode = models.CharField(max_length=20, null=True, blank=True)
    product_brand = models.CharField(max_length=100, default="Unknown")

    def __str__(self):
        return f"Order {self.id} - {self.status}"
    
    def save(self, *args, **kwargs):
        if not self.pk:
            if not self.estimated_delivery:
                self.estimated_delivery = timezone.now() + timedelta(days=5)
        else:
        # We use a try-except to handle the very first save where old_order might not exist
            try:
                old_order = Order.objects.get(pk=self.pk)
                if old_order.status != self.status:
                    if self.status == 'Shipped':
                        self.shipped_at = timezone.now()
                elif self.status == 'Delivered':
                    self.delivered_at = timezone.now()
                
                # Trigger notification for Shipped, Delivered, etc.
                # We skip 'Pending' and 'Confirmed' (handled by views.py) to avoid double emails
                if self.status not in ['Pending', 'Confirmed']:
                    self.send_order_notification(self.status)
            except Order.DoesNotExist:
                pass

        super().save(*args, **kwargs)

        

    def send_order_notification(self, status_type):
        """Helper to send Email and WhatsApp to Guest or Registered Users"""
    
    # 1. Determine Recipient Data (Priority: Checkout Form Data -> User Profile)
        customer_name = self.full_name or (self.user.username if self.user else "Customer")
        email = self.email or (self.user.email if self.user else None)
        phone = self.phone_number or (getattr(self.user, 'phone_number', None) if self.user else None)

        if not email:
            print("❌ No email found for this order. Skipping notification.")
            return

        track_url = f"http://127.0.0.1:8000/track-order/{self.order_id}/"
    
        subject = f"Order {status_type}: #{self.order_id}"
        message = (
            f"Hi {customer_name},\n\n"
            f"Update: Your order is now {status_type}.\n"
            f"You can track your progress here: {track_url}\n\n"
            f"Thank you for shopping with AI Store!"
        )

    # 2. SEND EMAIL
        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=False,
            )
            print(f"✅ Email sent successfully to {email}")
        except Exception as e:
            print(f"❌ Email failed for {email}: {e}")

    # 3. SEND WHATSAPP
        if phone:
            try:
            # Ensure your phone number format is correct for Twilio (+91...)
                print(f"📱 Sending WhatsApp to {phone}...")
            # client.messages.create(body=message, from_=settings.TWILIO_WHATSAPP_NUMBER, to=f'whatsapp:{phone}')
            except Exception as e:
                print(f"❌ WhatsApp failed for {phone}: {e}")

    def send_whatsapp_update(self):
        try:
            account_sid = os.getenv('TWILIO_ACCOUNT_SID')
            auth_token = os.getenv('TWILIO_AUTH_TOKEN')
            client = Client(account_sid, auth_token)

            domain = os.getenv('MY_DOMAIN', 'https://m1h3zc72-8000.inc1.devtunnels.ms') 
            track_url = f"{domain}/track-order/{self.order_id}/"

            from_whatsapp_number = 'whatsapp:+14155238886' 
            to_whatsapp_number = f'whatsapp:+91{self.phone_number}'

            message = client.messages.create(
                body=f"Order Update! Hi {self.full_name}, your Order #{self.id} is {self.status}. Track it here: {track_url}",
                from_=from_whatsapp_number,
                to=to_whatsapp_number
            )
            print(f"WhatsApp Success! SID: {message.sid}")
        except Exception as e:
            print(f"WhatsApp Error: {e}")

    def get_total(self):
        return sum(item.get_total_item_price() for item in self.items.all())

# --- 4. Order Items ---
class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)

    def get_total_item_price(self):
        return self.quantity * self.price

# --- 5. User Activity & Contact ---
class UserActivity(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    score = models.IntegerField(default=1)

class ContactMessage(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)