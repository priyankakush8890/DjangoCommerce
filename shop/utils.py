from io import BytesIO
from django.http import HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa

# shop/utils.py
from io import BytesIO
from django.template.loader import get_template
from xhtml2pdf import pisa

def render_to_pdf(template_src, context_dict={}):
    template = get_template(template_src)
    html = template.render(context_dict)
    result = BytesIO()
    
    # FIX: Encode the HTML to UTF-8 before passing it to pisa
    pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result, encoding='UTF-8')
    
    if not pdf.err:
        return result.getvalue()
    return None

from twilio.rest import Client
from django.conf import settings
def send_twilio_message(to_number, body):
    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    
    # 🚨 HARDCODE YOUR SANDBOX NUMBER HERE FOR TESTING
    # Use the exact number shown in your Twilio Console Sandbox page
    sender = "whatsapp:+14155238886" 
    
    # Format the recipient
    to_number = str(to_number).strip()
    if not to_number.startswith('+'):
        to_number = f"+91{to_number}"
    
    formatted_to = f"whatsapp:{to_number}"

    print(f"DEBUG: Attempting to send FROM {sender} TO {formatted_to}")

    try:
        message = client.messages.create(
            from_=sender, 
            body=body,
            to=formatted_to
        )
        print(f"✅ WhatsApp Sent! SID: {message.sid}")
        return message.sid
    except Exception as e:
        print(f"❌ Twilio Error Details: {e}")
        return None