from rest_framework import serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from .models import ProductData


class CustomPagination(PageNumberPagination):
    def get_paginated_response(self, data):
        return Response({
            'links': {
                'next': self.get_next_link(),
                'previous': self.get_previous_link()
            },
            'count': self.page.paginator.count,
            'total_number_of_pages':self.page.paginator.num_pages,
            'results': data,
        })

class ProductDataSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = ProductData
        fields = ['id', 'name','sku', 'description']


