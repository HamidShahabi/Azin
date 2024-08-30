from django.urls import path
from .views import FileListView, FileUploadView, FileDownloadView, FileDeleteView, create_chat_room, list_chat_rooms, \
    chat_room, download_chat_file

urlpatterns = [
    path('', FileListView.as_view(), name='list_files'),
    path('upload/', FileUploadView.as_view(), name='upload_file'),
    path('download/<str:file_name>/', FileDownloadView.as_view(), name='download_file'),
    path('delete/<str:file_name>/', FileDeleteView.as_view(), name='delete_file'),
    path('create-room/', create_chat_room, name='create_chat_room'),
    path('rooms/', list_chat_rooms, name='list_chat_rooms'),
    path('room/<str:room_name>/', chat_room, name='chat_room'),
    path('download/<str:bucket_name>/<str:file_name>/', download_chat_file, name='download_chat_file'),

]
