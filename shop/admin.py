from django.contrib import admin
from .models import Product, Order, OrderItem, UserActivity, ContactMessage, Coupon

# 1. Coupon Admin
@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ['code', 'discount_percent', 'active', 'valid_from', 'valid_to']
    list_filter = ['active', 'valid_to']
    search_fields = ['code']

# 2. Product Admin
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'category', 'stock')
    search_fields = ('name', 'category')
    list_filter = ('category',)

# 3. OrderItem Inline (Order ke andar products dikhane ke liye)
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'price', 'quantity')

# 4. Order Admin (Merged & Corrected)
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    # list_display mein wo fields rakhein jo aapne naye Order model mein banaye hain
    list_filter = ['status', 'paid', 'created_at']
    search_fields = ['order_id', 'full_name', 'email', 'user__username']
    readonly_fields = ('order_id', 'payment_id', 'created_at')
    # Add 'shipped_at' and 'estimated_delivery' to this list
    list_display = ('id', 'full_name','amount', 'status', 'paid', 'shipped_at', 'estimated_delivery', 'created_at')
    
    # This allows you to edit the status and dates directly from the list view
    list_editable = ('status', 'shipped_at', 'estimated_delivery') 
    
    inlines = [OrderItemInline]

# 5. User Activity Admin
@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ('user', 'product', 'score')

# 6. Contact Message Admin
@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'created_at')
    readonly_fields = ('created_at',)