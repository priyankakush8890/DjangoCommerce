import streamlit as st
import os
import django
import sys
from pathlib import Path
from dotenv import load_dotenv
from google import genai

## 1. SETUP PATHS
# This identifies the 'ecommercepro' folder
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

# 2. SETUP DJANGO
# CHANGE THIS LINE: It must point to 'core', not 'ecommercepro'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings') 
django.setup()
# 3. IMPORT MODELS (Only after django.setup())
from shop.models import Order 

# 4. SETUP AI CLIENT
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


st.set_page_config(page_title="Shop Cart AI Assistant", page_icon="🛍️")
st.title("🛍️ Shop Cart AI Assistant")
st.markdown("Enter your phone number to track your orders.")

# --- 3. SESSION STATE FOR CHAT ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- 4. SIDEBAR FOR USER IDENTIFICATION ---
with st.sidebar:
    user_phone = st.text_input("Enter Registered Phone Number", placeholder="e.g. 9876543210")
    if st.button("Clear Chat"):
        st.session_state.messages = []
        st.rerun()

# --- 5. DATA RETRIEVAL LOGIC ---
def get_order_context(phone):
    # Search Django database for orders matching the phone number
    orders = Order.objects.filter(phone_number__contains=phone)
    if orders.exists():
        context = "User's Order History:\n"
        for o in orders:
            context += f"- ID: {o.order_id}, Status: {o.status}, Brand: {o.product_brand}, Delivery: {o.estimated_delivery}\n"
        return context
    return "The user has no orders in our records."

# --- 6. CHAT UI ---
# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# User Input
if prompt := st.chat_input("How can I help you today?"):
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generate AI Response
    if not user_phone:
        response_text = "Please enter your phone number in the sidebar so I can find your orders!"
    else:
        with st.spinner("Thinking..."):
            db_context = get_order_context(user_phone)
            
            full_prompt = f"""
            You are 'Shop Cart Support AI'. 
            DATABASE CONTEXT: {db_context}
            USER QUESTION: {prompt}
            
            INSTRUCTIONS:
            - If they ask for order status, look at the ID they mention.
            - If they don't provide an ID, list their orders and ask which one they need help with.
            - Be polite and professional.
            """
            
            try:
                response = client.models.generate_content(
                    model="gemini-3-flash-preview",
                    contents=full_prompt
                )
                response_text = response.text
            except Exception as e:
                response_text = f"Error connecting to AI: {e}"

    # Add AI response to history
    st.session_state.messages.append({"role": "assistant", "content": response_text})
    with st.chat_message("assistant"):
        st.markdown(response_text)