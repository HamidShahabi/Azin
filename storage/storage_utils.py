import hashlib
import logging
import os
from tempfile import NamedTemporaryFile

from storage.s3_utils import S3Facade
from storage.es_utils import ElasticsearchFacade
from storage.es_mappings import HASH_INDEX_MAPPING
import uuid


audit_logger = logging.getLogger('audit_logger')
error_logger = logging.getLogger('error_logger')


class StorageFacade:
    def __init__(self):
        try:
            self.s3_facade = S3Facade()
            self.es_facade = ElasticsearchFacade()
            self.index_name = 'files_index'
            audit_logger.info("Initialized StorageFacade with S3 and Elasticsearch facades.")

            if not self.es_facade.es_client.indices.exists(index=self.index_name):
                self.es_facade.create_index(self.index_name, es_mappings=HASH_INDEX_MAPPING)
        except Exception as e:
            error_logger.error(f"Failed to initialize StorageFacade: {str(e)}")
            raise

    @staticmethod
    def calculate_file_hash(file_path):
        """Calculate the SHA-256 hash of a file."""
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception as e:
            error_logger.error(f"Failed to calculate file hash for {file_path}: {str(e)}")
            raise

    def upload_file(self, file_path, bucket_name, object_name=None, metadata=None):
        """Upload a file to S3, or create a link if the file already exists."""
        try:
            # Calculate the file's hash
            file_hash = self.calculate_file_hash(file_path)

            # Check if the file already exists in Elasticsearch
            query = {"query": {"term": {"file_hash": file_hash}}}
            existing_files = self.es_facade.search(self.index_name, query)

            if existing_files['hits']['total']['value'] > 0:
                # File with the same hash already exists, create a link
                existing_file = existing_files['hits']['hits'][0]['_source']
                existing_s3_object_name = existing_file['s3_object_name']

                # Create a symbolic link in S3
                link_object_name = object_name or f"{file_path.rsplit('/', 1)[-1]}"

                # Check for collision and generate a unique name if needed
                if self.s3_facade.object_exists(bucket_name, link_object_name):
                    link_object_name = self.generate_unique_name(link_object_name)

                s3_object_name = self.s3_facade.create_link(bucket_name, existing_s3_object_name, link_object_name)
                # Index the file metadata in Elasticsearch, including the file name
                document = {
                    "file_name": object_name,
                    "file_hash": file_hash,
                    "s3_object_name": s3_object_name,
                    "metadata": metadata or {}
                }
                self.es_facade.index_document(self.index_name, document)
                audit_logger.info(
                    f"File '{file_path}' already exists in S3 as '{existing_s3_object_name}'. "
                    f"Link created as '{link_object_name}'.")

                return existing_s3_object_name, link_object_name

            # If no duplicates, upload the file
            object_name = object_name or file_path.rsplit('/', 1)[-1]
            s3_object_name = self.s3_facade.upload_file(bucket_name, file_path, object_name)

            # Index the file metadata in Elasticsearch, including the file name
            document = {
                "file_name": object_name,
                "file_hash": file_hash,
                "s3_object_name": s3_object_name,
                "metadata": metadata or {}
            }
            self.es_facade.index_document(self.index_name, document)

            audit_logger.info(f"File '{file_path}' uploaded to S3 as '{s3_object_name}' and indexed in Elasticsearch.")

            return s3_object_name, None
        except Exception as e:
            error_logger.error(f"Failed to upload file '{file_path}': {str(e)}")
            raise

    def download_file(self, file_name, bucket_name):
        """Download a file from S3 based on its object name. If the file is a link, download the original file."""
        try:
            # Construct the s3_object_name in the pattern bucket_name/file_name
            s3_object_name = f"{bucket_name}/{file_name}"

            # Search for the file in Elasticsearch using the s3_object_name
            query = {"query": {"term": {"s3_object_name": s3_object_name}}}
            result = self.es_facade.search(self.index_name, query)

            if result['hits']['total']['value'] == 0:
                raise Exception(f"No file found with object name '{s3_object_name}'")

            # Get the S3 object name (should match s3_object_name)
            s3_object_name = result['hits']['hits'][0]['_source']['s3_object_name']

            # Extract the file extension from the object_name
            file_extension = os.path.splitext(file_name)[1]

            # Create a temporary file with the correct extension
            with NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
                temp_file_path = temp_file.name
                self.s3_facade.download_file(bucket_name, file_name, temp_file_path)

            # Check if the file is a symbolic link
            original_key = self.s3_facade.resolve_link(bucket_name, file_name)
            if original_key:
                audit_logger.info(f"File '{file_name}' is a link. Resolving to original object '{original_key}'.")

                # Split the original_key to get the bucket_name and file_name
                parts = original_key.split('/')
                new_bucket_name = parts[0]  # The first part is the bucket name
                new_file_name = parts[-1]  # The last part is the file name (object name)

                audit_logger.info(f"Resolved to bucket '{new_bucket_name}' and file '{new_file_name}'.")

                # Now use the new bucket name and file name to download the file
                self.s3_facade.download_file(new_bucket_name, new_file_name, temp_file_path)

            audit_logger.info(f"File '{file_name}' downloaded successfully with extension '{file_extension}'.")

            # Return the path to the temporary file and the file name
            return temp_file_path, file_name
        except Exception as e:
            error_logger.error(f"Failed to download file '{file_name}': {str(e)}")
            raise

    def delete_file(self, file_name, bucket_name):
        """Delete a file from S3 and Elasticsearch based on its name."""
        try:
            # Construct the s3_object_name in the pattern bucket_name/file_name
            s3_object_name = f"{bucket_name}/{file_name}"

            # Search for the file in Elasticsearch using the s3_object_name
            query = {"query": {"term": {"s3_object_name": s3_object_name}}}
            result = self.es_facade.search(self.index_name, query)

            if result['hits']['total']['value'] == 0:
                raise Exception(f"No file found with name '{file_name}'")

            # Get the S3 object name
            s3_object_name = result['hits']['hits'][0]['_source']['s3_object_name']

            # Download the file to a temporary location
            with NamedTemporaryFile(delete=False) as temp_file:
                temp_file_path = temp_file.name
                self.s3_facade.download_file(bucket_name, s3_object_name, temp_file_path)

            # Calculate the file's hash
            file_hash = self.calculate_file_hash(temp_file_path)

            # Check if there are any links to this file
            link_query = {"query": {"term": {"metadata.original-key": s3_object_name}}}
            link_results = self.es_facade.search(self.index_name, link_query)

            if link_results['hits']['total']['value'] > 0:
                # Copy the original file's content to the linked files before deletion
                original_file_content = self.s3_facade.get_object_body(s3_object_name, bucket_name)
                for link in link_results['hits']['hits']:
                    linked_s3_object_name = link['_source']['s3_object_name']
                    self.s3_facade.upload_object_body(linked_s3_object_name, original_file_content, bucket_name)
                    audit_logger.info(
                        f"Copied content from '{s3_object_name}' to linked object '{linked_s3_object_name}'.")

            # Delete the original file from S3
            self.s3_facade.delete_file(bucket_name, s3_object_name)

            # Remove the document from Elasticsearch
            doc_id = result['hits']['hits'][0]['_id']
            self.es_facade.delete_document(self.index_name, doc_id)

            audit_logger.info(f"File with name '{file_name}' deleted from S3 and Elasticsearch.")

            return f"File '{s3_object_name}' deleted."
        except Exception as e:
            error_logger.error(f"Failed to delete file '{file_name}': {str(e)}")
            raise

    def list_files(self, bucket_name, prefix=None):
        """List files in the S3 bucket."""
        try:
            files = self.s3_facade.list_files(bucket_name, prefix)
            audit_logger.info(f"Files listed in bucket '{bucket_name}' with prefix '{prefix}': {files}")
            return files
        except Exception as e:
            error_logger.error(f"Failed to list files in bucket '{bucket_name}' with prefix '{prefix}': {str(e)}")
            raise

    def generate_unique_name(self, object_name):
        """Generate a unique name by appending a UUID to the original name."""
        base_name, extension = object_name.rsplit('.', 1) if '.' in object_name else (object_name, '')
        unique_name = f"{base_name}_{uuid.uuid4().hex}"
        if extension:
            unique_name = f"{unique_name}.{extension}"
        return unique_name