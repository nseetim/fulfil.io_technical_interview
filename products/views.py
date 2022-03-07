import csv
import os
from itertools import islice

from django.shortcuts import render
from django.db.models.query_utils import Q

from rest_framework import status
from rest_framework.response import Response
from rest_framework.parsers import FileUploadParser
from rest_framework.decorators import api_view, parser_classes

from django_eventstream import send_event

from .models import ProductData
from .serializers import ProductDataSerializer, CustomPagination

from dask import dataframe as ddf
from dask.diagnostics import ProgressBar

"""
    The first endpoint we have here would load the data in the file uploaded into the Database,
    the idea is to make sure that the process is as Performant and efficient as possible and and not just effective

    We would be making use of the standard Python Libraries as much as possible except in cases where not possible 
    this is because they are in many cases generally much more efficient and performant than external libraries

    This endpoint is to also carry out deduplication according to the Story 1, so we would rather deduplicate the data file then carry out bulk create action to the database

    Since it was'nt stated I would work with the following assumptions for this endpoint
        1. Uploaded files can not be retireved by the user or client
        2. We are not obligated to keep original copies of the uploaded files
        3. After parsing the uploaded file we can delete the file
        4. Althought the sample file isnt a really large one, we have to make provision for such a scenerio so files would be processed in chunks
        5. While the system is built to handle large data uploads it is also constrained by the limits of the python data structures such as lists,
           dictionaries etc which are used to implement the solution, so in this case some restrictions would be set on the number of entries allowed in a single file,
           more than 8million entries in a single file and it should be considered being split in two and uploaded, if required a feature can be added to the system to 
           allow for uploading and handling of multiple files simultenously

    The Second part of this Story is that there should be an endpoint to get upload progress from the server,
        1. For this we would be using the Django SSE tool which is built on top of Django channels which allows or provides asynchronous support for Django
        2. We would use Redis to hold the state of upload so that when the endpoint for getting the progress status for a particular file upload is called the 
           status of the upload would be fetched from the Redis server
"""

########################################### UTILITY FUNCTION ####################################

def file_upload_handler(request,uploaded_file):
    parsed_sku_set = set() # We use set to avoid the possiblility of duplicates and to leverage on its performance advantage
    parsed_sku_list = list() # Keep the entry mapped to its sku as a key value pair to help updating or overiding
    parsed_sku_dict = dict()
    field_names = ['name', 'sku', 'description']


    # Load files in chunks to avoid overwhelming the server memory in case of large files while at the same time eliminating duplicate files
    filename = f'../tmp/{uploaded_file.name}{request.user}.csv'
    with open(filename, 'w') as deduped_file:
        for file_chunk in uploaded_file.chunks():
            file_chunk_dict = csv.DictReader(file_chunk)
            for entry in file_chunk_dict:
                if entry['sku'].lower() not in parsed_sku_set:
                    parsed_sku_set.add(entry['sku'].lower())
                    parsed_sku_dict[entry['sku']] = entry
                    parsed_sku_list.append({entry['sku']:entry})
                for listitem in parsed_sku_list:
                    for key_, value_, in listitem.items():
                        if key_ == entry['sku']:
                            parsed_sku_list.remove(listitem)
                parsed_sku_dict[entry['sku']] = entry
                parsed_sku_list.append({entry['sku']:entry})
                
        new_file_writer = csv.DictWriter(f=deduped_file, field_names=field_names)
        new_file_writer.writeheader()
        new_file_writer.writerows(parsed_sku_list)
        file_size = deduped_file.seek(0, os.SEEK_END)
    return [filename, file_size]


def write_bulk_to_db(request,file_name,file_size):
    batch_size = 100
    count = 1

    # Having used the builtin python libraries we would be using an external library here, Dask to read the csv file in chunks and write to the database
    db_objs = [ProductData(
        user=request.user,
        name=entry['name'],
        sku=entry['sku'],
        description=entry['description']
    ) for entry in ddf.read_csv(file_name, blocksize=1000)]

    while True:
        batch = list(islice(db_objs, batch_size))
        if not batch:
            send_event(channel='uploadprogress',event_type='message', data={'progress':"File Upload Complete"})
            break
        ProductData.objects.bulk_create(batch, batch_size)
        progress_bar = ProgressBar()
        progress_bar.register()
        upld_sts = batch_size/file_size * 100
        count += 1
        send_event(channel='uploadprogress',event_type='message', data={'progress': f"File Upload is {upld_sts}% Complete"})
    return "Upload complete"
    




###################################### END OF UTILITY FUNCTION ##################################



@api_view(['POST',])
@parser_classes([FileUploadParser])
async def file_upload(request):
    file_to_handle = request.data['file']

    if not file_to_handle:
        return Response(
            {
                'error_message':'A file must be uploaded, non was uploaded'
            },status=status.HTTP_400_BAD_REQUEST
        )
    cleaned_file = file_upload_handler(request=request, uploaded_file=file_to_handle)
    upload_response = await write_bulk_to_db(request=request,file_name=cleaned_file[0],file_size=cleaned_file[1])
    if upload_response == "Upload complete":
        return Response(
            {
                "message":"The upload completed successfully"
            },status=status.HTTP_200_OK
        )
    return Response({
        'error':"The file upload was not successful"
    },status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET','POST','PUT','DELETE'])
def crud_operations(request):
    
    if request.method == 'GET':
        filter_set = ['sku','name','description']
        filter_by = request.query_params.get('filter_by')
        filter_entry = request.query_params.get('filter_entry')
        if filter_by not in filter_set:
            return Response({'message':'Your filter_by option is not valid, please check and supply a correct option'},status=status.HTTP_400_BAD_REQUEST)

        if not filter_by:
            all_products = ProductData.objects.all()
            paginator = CustomPagination()
            paginator.page_size = 20
            result_page = paginator.paginate_queryset(all_products, request)
            product_result_serializer = ProductDataSerializer(result_page, many=True)
            return paginator.get_paginated_response(product_result_serializer.data)
        if filter_by:
            filtered_list = ProductData.objects.filter(Q(name=filter_by)|Q(sku=filter_by)|Q(description=filter_by))
            if filtered_list:
                paginator = CustomPagination()
                paginator.page_size = 20
                result_page = paginator.paginate_queryset(filtered_list, request)
                product_result_serializer = ProductDataSerializer(result_page, many=True)
                return paginator.get_paginated_response(product_result_serializer.data)
        return Response({'message':'Sorry no records found for that input'},status=status.HTTP_404_NOT_FOUND)

    if request.method == 'POST':
        product_data = request.data.get('product_data')
        if not product_data:
            return Response({'message':'A product data is required'})
        name = request.data.get('name')
        sku = request.data.get('sku')
        description = request.data.get('sku')
        try:
            duped_sku = ProductData.objets.get(sku)
        except ProductData.DoesNotExist:
            ProductData.bjects.create(
                name=name, sku=sku, description=description
            )
            return Response({'message':'Record successfully created'},status=status.HTTP_201_CREATED)

    if request.method == 'PUT':
        product_data = request.data.get('product_data')
        if not product_data:
            return Response({'message':'A product data is required'})
        name = request.data.get('name')
        sku = request.data.get('sku')
        description = request.data.get('sku')
        try:
            sku_to_update = ProductData.objets.get(sku)
            sku_to_update.name = name
            sku_to_update.sku = sku
            sku_to_update.description = description
        except ProductData.DoesNotExist:
            return Response({'message':'Those entries dont exist'},status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'DELETE':
        item_to_delete_id = request.query_params.get('id')
        if not item_to_delete_id:
            return Response({
                'error':'The id of the product to be deleted is required'
            },status=status.HTTP_400_BAD_REQUEST)

        try:
            product_to_delete = ProductData.objects.get(item_to_delete_id).delete()
        except ProductData.DoesNotExist:
            return Response(
                {'message':'That product doesnt exist'},status=status.HTTP_404_NOT_FOUND
            )
@api_view(['DELETE',])
def dangerous_delete(request):
    ProductData.objects.all().delete()
    return Response({'message':'You have successfully deleted all the products on your account'})



