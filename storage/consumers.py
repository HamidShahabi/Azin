import json
import os
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from .models import ChatRoom, Message
from django.contrib.auth.models import User
from .storage_utils import StorageFacade


class ChatConsumer(AsyncWebsocketConsumer):
    storage_facade = StorageFacade()

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
    async def receive(self, text_data=None, bytes_data=None):
        user = self.scope['user']

        if text_data:
            text_data_json = json.loads(text_data)
            if 'message' in text_data_json:
                message = text_data_json['message']

                if message:
                    # Save the message in the database
                    await self.save_message(self.room_name, user, message)

                    # Send message to room group
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'chat_message',
                            'message': message,
                            'username': user.username,
                            'timestamp': self.get_current_timestamp()
                        }
                    )
            elif 'file_name' in text_data_json:
                self.file_name = text_data_json['file_name']  # Store the file name for use with binary data

        elif bytes_data and self.file_name:
            # Handle binary file data
            file_path = os.path.join('/tmp', self.file_name)  # Temporarily save the file

            with open(file_path, 'wb') as f:
                f.write(bytes_data)

            # Upload the file using storage_utils
            s3_object_name = await sync_to_async(self.storage_facade.upload_file)(file_path, user.username)
            # Remove the file after uploading it to storage
            os.remove(file_path)

            # Generate the download link
            file_link = f'/download/{user.username}/{s3_object_name}'

            # Save the file message to the database
            await self.save_message(self.room_name, user,
                                    f'shared a file: <a href="{file_link}">{self.file_name}</a>')

            # Send the file link to the room group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': f'shared a file: <a href="{file_link}">{self.file_name}</a>',
                    'username': user.username,
                    'timestamp': self.get_current_timestamp()
                }
            )
            self.file_name = None  # Reset file name after handling the file

    async def chat_message(self, event):
        message = event['message']
        username = event['username']
        timestamp = event['timestamp']

        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'message': f'{username}: {message} ({timestamp})'
        }))

    @sync_to_async
    def save_message(self, room_name, user, message):
        room = ChatRoom.objects.get(name=room_name)
        Message.objects.create(room=room, sender=user, content=message)

    def get_current_timestamp(self):
        from datetime import datetime
        return datetime.now().strftime('%H:%M')