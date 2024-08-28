from django.urls import path
from .views import FileListView, FileUploadView, FileDownloadView, FileDeleteView

urlpatterns = [
    path('', FileListView.as_view(), name='list_files'),
    path('upload/', FileUploadView.as_view(), name='upload_file'),
    path('download/<str:file_name>/', FileDownloadView.as_view(), name='download_file'),
    path('delete/<str:file_name>/', FileDeleteView.as_view(), name='delete_file'),
]
