from django.urls import path, include
from products.views import dangerous_delete, crud_operations, file_upload

urlpatterns = [
    path('', crud_operations, name="crudoperations"),
    path('dangerous_delete', dangerous_delete, name='dangerousdelete'),
    path('upload', file_upload, name='fileupload')
]