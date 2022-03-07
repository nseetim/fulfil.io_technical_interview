"""
ASGI config for fulfil_testapp project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.1/howto/deployment/asgi/
"""

import os
import django
from django.core.asgi import get_asgi_application
from django.conf.urls import url
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import django_eventstream

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fulfil_testapp.settings')

#application = get_asgi_application()

application = ProtocolTypeRouter({
    'http': URLRouter([
        url(r'^uploadprogress/', AuthMiddlewareStack(URLRouter(django_eventstream.routing.urlpatterns)), { 'channels': ['uploadprogress'] }),
        url(r'', get_asgi_application()),
    ]),
})
