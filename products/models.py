import requests

from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from rest_framework.response import Response

# Create your models here.
class UserFIelds(User):
    prod_webhook = models.URLField()

class ProductData(models.Model):
    owner = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=255,unique=True)
    description = models.TextField()

@receiver(post_save, sender=ProductData)
def notify_about_product_creation(sender, instance=None, created=False, **kwargs):
    if created:
        url = instance.owner.prod_webhook
        data = {
            'operation_type':'creation',
            'details':{
                'id':instance.id,
                'name':instance.name,
                'sku':instance.sku,
                'description':instance.description
            }
        }
        requests.post(url=url,data=data)
    url = instance.owner.prod_webhook
    data = {
        'operation_type':'update',
        'details':{
            'id':instance.id,
            'name':instance.name,
            'sku':instance.sku,
            'description':instance.description
        }
    }
    requests.post(url=url,data=data)