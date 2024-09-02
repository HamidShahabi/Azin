import mimetypes
import time

from django.contrib.auth.models import User
from django.views.generic import ListView, CreateView, DeleteView, View
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.http import HttpResponse, HttpResponseNotFound, FileResponse
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator

from storage.models import ChatRoom, Message
from storage.storage_utils import StorageFacade
import os

storage_facade = StorageFacade()


@method_decorator(login_required, name='dispatch')
class FileListView(ListView):
    template_name = 'storage/list_files.html'
    context_object_name = 'files'

    def get_queryset(self):
        bucket_name = self.request.user.username
        return storage_facade.list_files(bucket_name)


@method_decorator(login_required, name='dispatch')
class FileUploadView(View):
    template_name = 'storage/upload_file.html'

    def post(self, request, *args, **kwargs):
        file = request.FILES['file']
        file_path = os.path.join('/tmp', file.name)  # Save file temporarily to calculate hash
        with open(file_path, 'wb+') as destination:
            for chunk in file.chunks():
                destination.write(chunk)

        bucket_name = request.user.username
        storage_facade.upload_file(file_path, bucket_name)

        os.remove(file_path)  # Clean up the temporary file
        storage_facade.es_facade.refresh_index(storage_facade.index_name)
        return redirect('list_files')

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name)


@method_decorator(login_required, name='dispatch')
class FileDownloadView(View):
    def get(self, request, file_name, *args, **kwargs):
        try:
            bucket_name = request.user.username
            # Construct the s3_object_name in the pattern bucket_name/file_name
            s3_object_name = f"{bucket_name}/{file_name}"

            # Search for the file in Elasticsearch using the s3_object_name
            query = {"query": {"term": {"s3_object_name": s3_object_name}}}
            result = storage_facade.es_facade.search(storage_facade.index_name, query)

            if result['hits']['total']['value'] == 0:
                raise Exception(f"No file found with name '{file_name}'")

            # Get the original file name from the metadata
            original_file_name = result['hits']['hits'][0]['_source']['metadata'].get('original-file-name', file_name)

            # Download the file from S3
            temp_file_path, _ = storage_facade.download_file(file_name, bucket_name)

            # Determine the correct MIME type
            mime_type, _ = mimetypes.guess_type(original_file_name)
            mime_type = mime_type or 'application/octet-stream'

            # Open the temporary file and serve it as an HTTP response
            with open(temp_file_path, 'rb') as file:
                response = HttpResponse(file.read(), content_type=mime_type)
                response['Content-Disposition'] = f'attachment; filename="{original_file_name}"'
                response['Content-Length'] = os.path.getsize(temp_file_path)

            # Clean up the temporary file after serving it
            os.remove(temp_file_path)

            return response
        except Exception as e:
            return HttpResponseNotFound(f"File not found: {str(e)}")


@method_decorator(login_required, name='dispatch')
class FileDeleteView(DeleteView):
    template_name = 'storage/delete_file.html'
    success_url = reverse_lazy('list_files')

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {'file_name': self.kwargs['file_name']})

    def post(self, request, *args, **kwargs):
        file_hash = self.kwargs['file_name']
        bucket_name = request.user.username
        storage_facade.delete_file(file_hash, bucket_name)
        return redirect(self.success_url)


@login_required
def create_chat_room(request):
    if request.method == "POST":
        room_name = request.POST['room_name']
        user_ids = request.POST.getlist('members')
        new_room = ChatRoom.objects.create(name=room_name)
        new_room.members.add(request.user)
        new_room.members.add(*user_ids)
        return redirect('chat_room', room_name=new_room.name)

    users = User.objects.exclude(id=request.user.id)
    return render(request, 'create_chat_room.html', {'users': users})


@login_required
def list_chat_rooms(request):
    rooms = ChatRoom.objects.filter(members=request.user)
    return render(request, 'list_chat_rooms.html', {'rooms': rooms})


@login_required
def chat_room(request, room_name):
    room = get_object_or_404(ChatRoom, name=room_name)
    messages = Message.objects.filter(room=room).order_by('timestamp')
    return render(request, 'chat_room.html', {
        'room_name': room_name,
        'messages': messages
    })


def download_chat_file(request, bucket_name, file_name):
    try:
        # Construct the s3_object_name in the pattern bucket_name/file_name
        s3_object_name = f"{bucket_name}/{file_name}"

        # Search for the file in Elasticsearch using the s3_object_name
        query = {"query": {"term": {"s3_object_name": s3_object_name}}}
        result = storage_facade.es_facade.search(storage_facade.index_name, query)

        if result['hits']['total']['value'] == 0:
            raise Exception(f"No file found with name '{file_name}'")

        # Get the original file name from the metadata
        original_file_name = result['hits']['hits'][0]['_source']['metadata'].get('original-file-name', file_name)
        # Download the file from object storage
        temp_file_path, _ = storage_facade.download_file(file_name, bucket_name)

        # Open the file and serve it as a response
        file_handle = open(temp_file_path, 'rb')
        response = FileResponse(file_handle, content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{original_file_name}"'
        os.remove(temp_file_path)
        return response
    except Exception as e:
        return HttpResponseNotFound(f"File not found: {str(e)}")
