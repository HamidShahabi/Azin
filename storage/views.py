import mimetypes

from django.views.generic import ListView, CreateView, DeleteView, View
from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.http import HttpResponse, HttpResponseNotFound
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
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
