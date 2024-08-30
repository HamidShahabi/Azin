import json
import os
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from .storage_utils import StorageFacade
from django.contrib.auth.models import User

class ChatConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(args, kwargs)
        self.storage_facade = StorageFacade()

    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f'chat_{self.room_name}'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Receive message from WebSocket
    async def receive(self, text_data):
        print("Received data:", text_data)  # Debugging output
        data = json.loads(text_data)
        print("Parsed data:", data)
        data = json.loads(text_data)
        message = data.get('message')
        file_data = data.get('file')
        user = self.scope['user']
        room_name = self.room_name

        if file_data:
            # Handle file upload
            file_name = file_data['name']
            file_content = file_data['content']
            file_path = os.path.join('/tmp', file_name)  # Temporarily save the file

            with open(file_path, 'wb') as f:
                f.write(file_content.encode('utf-8'))

            # Upload the file using storage_utils
            s3_object_name, _ = await sync_to_async(self.storage_facade.upload_file)(file_path, user.username)

            # Generate the download link
            file_link = f'/download/{user.username}/{file_name}'

            # Send the file link to the room group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': f'{user.username} shared a file: <a href="{file_link}">{file_name}</a>',
                    'username': user.username,
                    'timestamp': self.get_current_timestamp()
                }
            )

        elif message:
            # Handle text message
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': message,
                    'username': user.username,
                    'timestamp': self.get_current_timestamp()
                }
            )

    async def chat_message(self, event):
        message = event['message']
        username = event['username']
        timestamp = event['timestamp']

        # Format the message as "username: message (timestamp)"
        formatted_message = f'{username}: {message} ({timestamp})'

        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'message': formatted_message
        }))

    def get_current_timestamp(self):
        from datetime import datetime
        return datetime.now().strftime('%H:%M')