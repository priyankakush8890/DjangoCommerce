from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Order
from .utils import send_twilio_message

@receiver(post_save, sender=Order)
def order_status_whatsapp_alert(sender, instance, created, **kwargs):
    # We only send notifications for updates (not when the order is first created)
    if not created:
        msg = ""
        
        if instance.status == 'Packed':
            msg = f"📦 Hi {instance.full_name}, your order #{instance.order_id} has been packed and is ready for shipment!"
            
        elif instance.status == 'Shipped':
            msg = f"🚚 Good news! Your order #{instance.order_id} has been shipped!"
            
        elif instance.status == 'On The Way':
            msg = f"📍 Update: Your order #{instance.order_id} is out for delivery and will reach you shortly."
            
        elif instance.status == 'Delivered':
            msg = f"✅ Delivered! Your package for Order #{instance.order_id} has been handed over. Enjoy your purchase!"

        # Only call the Twilio function if a message was actually set
        if msg:
            send_twilio_message(instance.phone_number, msg)
            print(f"WhatsApp notification triggered for status: {instance.status}")