import django_filters
from .models import Product

class ProductFilter(django_filters.FilterSet):
    # Defining specific lookups for a premium feel
    price__gt = django_filters.NumberFilter(field_name='price', lookup_expr='gte', label='Min Price')
    price__lt = django_filters.NumberFilter(field_name='price', lookup_expr='lte', label='Max Price')
    
    class Meta:
        model = Product
        # These are the fields that show up in your dropdown
        fields = {
            'category': ['exact'],
            'name': ['icontains'],
        }