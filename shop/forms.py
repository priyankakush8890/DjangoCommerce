from django import forms

class CheckoutForm(forms.Form):
    full_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'placeholder': 'Enter Full Name'}))
    email = forms.EmailField(widget=forms.TextInput(attrs={'placeholder': 'Email for updates'}))
    phone_number = forms.CharField(max_length=15, widget=forms.TextInput(attrs={'placeholder': 'WhatsApp Number (with country code)'}))
    address = forms.CharField(widget=forms.Textarea)