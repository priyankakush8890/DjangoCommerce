def cart_count(request):
    cart = request.session.get('cart', {})
    return {'cart_total_items': sum(cart.values())}