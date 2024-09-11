# Django Cloud Storage Service with WebSocket Support

This is a Django-based cloud storage service that supports real-time messaging and file management using WebSockets (via Django Channels) and object storage (MinIO). The project is dockerized for easy deployment and scalability.

## Features

- **Real-time Chat**: Users can chat in rooms with real-time updates powered by Django Channels.
- **File Management**: Users can upload, download, and manage files stored in MinIO.
- **Elasticsearch Integration**: Files are indexed and searchable using Elasticsearch.
- **User Authentication**: Built-in user authentication system with Django's auth module.
- **WebSocket Support**: Powered by Daphne, with Channels using the `InMemoryChannelLayer` for internal memory storage.

## Technologies Used

- **Django**: Backend framework.
- **Daphne**: HTTP, HTTP2, and WebSocket protocol server for ASGI and ASGI-HTTP.
- **Channels**: Adds WebSocket support to Django.
- **PostgreSQL**: Relational database for storing user data.
- **Elasticsearch**: For indexing and searching files.
- **MinIO**: S3-compatible object storage service.
- **Docker**: Containerization platform to easily deploy the application.

## Getting Started

### Prerequisites

- Docker and Docker Compose installed on your system.

### Setup Instructions

1. **Clone the repository**:
    ```bash
    git clone https://github.com/HamidShahabi/azin.git
    cd your-repo-name
    ```

2. **Build and start the Docker containers**:
    ```bash
    docker-compose up --build
    ```

3. **Access the application**:
    - Django: `http://localhost:8000`
    - MinIO Console: `http://localhost:9000` (Access Key: `minioadmin`, Secret Key: `minioadmin`)

4. **Create a superuser**:
    ```bash
    docker-compose exec django python manage.py createsuperuser
    ```

5. **Run Migrations**:
    ```bash
    docker-compose exec django python manage.py migrate
    ```

6. **Collect Static Files**:
    ```bash
    docker-compose exec django python manage.py collectstatic --noinput
    ```

### Environment Variables

Environment variables are set in the `docker-compose.yml` file for easy configuration.

- `DJANGO_SETTINGS_MODULE`: The Django settings module to use.
- `DATABASE_URL`: PostgreSQL database connection URL.
- `ES_HOST`: Elasticsearch host.
- `ES_PORT`: Elasticsearch port.
- `S3_ENDPOINT_URL`: MinIO endpoint URL.
- `S3_ACCESS_KEY_ID`: MinIO access key.
- `S3_SECRET_ACCESS_KEY`: MinIO secret key.
- `S3_BUCKET_NAME`: The bucket name to store files in MinIO.

### Project Structure

- `Dockerfile`: Defines the Docker image for the Django application.
- `docker-compose.yml`: Defines the services (Django, PostgreSQL, Elasticsearch, MinIO) and their configurations.
- `azin/`: Django project directory containing settings, URLs, and ASGI configuration.
- `storage/`: Contains the application logic, including models, views, and consumers for WebSocket handling.
- `templates/`: HTML templates used in the application.
- `static/`: Static files (CSS, JS, images).

### Running the Project in Development Mode

For development purposes, you can run the Django server locally without Docker:

1. **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2. **Run the development server**:
    ```bash
    python manage.py runserver
    ```

### WebSocket Configuration

The project uses **Daphne** to serve HTTP and WebSocket connections, and **InMemoryChannelLayer** is used for Channels' backend.

- **Daphne** is started with the following command in the Docker container:
    ```bash
    daphne -b 0.0.0.0 -p 8000 azin.asgi:application
    ```
- **InMemoryChannelLayer** is configured in the `settings.py`:
    ```python
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }
    ```

### License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

### Contributing

Contributions are welcome! Please open an issue or submit a pull request.

### Contact

For any inquiries or support, please contact [support@cloudstorage.com](mailto:support@cloudstorage.com).

---

Happy coding!
