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

                # Create the link and define the metadata with the original object's reference
                s3_object_name = self.s3_facade.create_link(bucket_name, existing_s3_object_name, link_object_name)

                # Define the metadata, including the original file name
                link_metadata = {
                    "original-key": existing_s3_object_name,
                    "linked-file-hash": file_hash,
                    "original-file-name": file_path.rsplit('/', 1)[-1]  # Store the original name
                }

                # Index the file metadata in Elasticsearch, including the file name and link metadata
                document = {
                    "file_name": link_object_name,
                    "file_hash": file_hash,
                    "s3_object_name": s3_object_name,
                    "metadata": link_metadata
                }
                self.es_facade.index_document(self.index_name, document)
                audit_logger.info(
                    f"File '{file_path}' already exists in S3 as '{existing_s3_object_name}'. "
                    f"Link created as '{link_object_name}' with metadata linking to the original object.")

                return existing_s3_object_name, link_object_name

            # If no duplicates, upload the file
            object_name = object_name or file_path.rsplit('/', 1)[-1]

            # If there's a conflict in the S3 bucket, generate a unique name
            if self.s3_facade.object_exists(bucket_name, object_name):
                object_name = self.generate_unique_name(object_name)

            s3_object_name = self.s3_facade.upload_file(bucket_name, file_path, object_name)

            # Define metadata for a new upload, including the original file name
            upload_metadata = {
                "original-key": None,  # No original key since this is the first upload
                "original-file-name": file_path.rsplit('/', 1)[-1]  # Store the original name
            }

            # Index the file metadata in Elasticsearch, including the file name
            document = {
                "file_name": object_name,
                "file_hash": file_hash,
                "s3_object_name": s3_object_name,
                "metadata": upload_metadata
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

            # Get the S3 object name and document ID
            s3_object_name = result['hits']['hits'][0]['_source']['s3_object_name']
            doc_id = result['hits']['hits'][0]['_id']

            # Handle links pointing to the original file
            self.handle_links_before_deletion(s3_object_name)

            # Delete the original file from S3
            self.s3_facade.delete_file(bucket_name, file_name)

            # Remove the document from Elasticsearch
            self.es_facade.delete_document(self.index_name, doc_id)

            audit_logger.info(f"File with name '{file_name}' deleted from S3 and Elasticsearch.")

            return f"File '{s3_object_name}' deleted."
        except Exception as e:
            error_logger.error(f"Failed to delete file '{file_name}': {str(e)}")
            raise

    def handle_links_before_deletion(self, s3_object_name):
        """Handle links pointing to the original file before deletion."""
        try:
            # Check if there are any links to this file
            link_query = {"query": {"term": {"metadata.original-key.keyword": s3_object_name}}}
            link_results = self.es_facade.search(self.index_name, link_query)

            if link_results['hits']['total']['value'] > 0:
                link_hits = link_results['hits']['hits']

                # Download the original file's content
                parts = s3_object_name.split('/')
                original_file_content = self.s3_facade.get_object_body(s3_object_name)

                if len(link_hits) > 1:
                    self.promote_one_link_to_original(link_hits, original_file_content)
                elif len(link_hits) == 1:
                    self.promote_single_link_to_original(link_hits[0], original_file_content)
        except Exception as e:
            error_logger.error(f"Failed to handle links before deletion for '{s3_object_name}': {str(e)}")
            raise

    def promote_one_link_to_original(self, link_hits, original_file_content):
        """Promote one of the symbolic links to be the new original file."""
        try:
            new_original_link = link_hits[0]
            new_original_s3_object_name = new_original_link['_source']['s3_object_name']
            new_original_doc_id = new_original_link['_id']

            # Upload the original file content to the new original link
            self.s3_facade.upload_object_body(new_original_s3_object_name, original_file_content)

            # Remove original-key metadata from the new original
            self.update_metadata_field(self.index_name, new_original_doc_id, 'original-key', None)

            # Update the rest of the links to point to the new original
            for link in link_hits[1:]:
                linked_s3_object_name = link['_source']['s3_object_name']
                link_doc_id = link['_id']

                # Update the original-key in metadata to point to the new original file
                self.update_metadata_field(self.index_name, link_doc_id, 'original-key', new_original_s3_object_name)

            audit_logger.info(
                f"Promoted '{new_original_s3_object_name}' to original file, copied original content, and updated other links.")
        except Exception as e:
            error_logger.error(f"Failed to promote one link to original for '{new_original_s3_object_name}': {str(e)}")
            raise

    def promote_single_link_to_original(self, single_link, original_file_content):
        """Promote a single symbolic link to be the new original file."""
        try:
            single_link_s3_object_name = single_link['_source']['s3_object_name']
            single_link_doc_id = single_link['_id']

            # Upload the original file content to the single link
            self.s3_facade.upload_object_body(single_link_s3_object_name, original_file_content)

            # Remove original-key metadata
            self.update_metadata_field(self.index_name, single_link_doc_id, 'original-key', None)

            audit_logger.info(
                f"Single link '{single_link_s3_object_name}' promoted to original file and original content copied.")
        except Exception as e:
            error_logger.error(
                f"Failed to promote single link to original for '{single_link_s3_object_name}': {str(e)}")
            raise
    def clear_original_key_metadata(self, doc_id):
        """Clear the original-key metadata from a document."""
        update_body = {"metadata": {"original-key": None}}
        self.es_facade.update_document(self.index_name, doc_id, update_body)

    def list_files(self, bucket_name, prefix=None):
        """List files in the S3 bucket and show original names with their sizes."""
        try:
            files = []
            s3_files = self.s3_facade.list_files(bucket_name, prefix)
            for s3_file in s3_files:
                # Get the file metadata (including size)
                head_response = self.s3_facade.s3_client.head_object(Bucket=bucket_name, Key=s3_file)
                file_size = head_response['ContentLength']  # Size in bytes
                s3_object_name = f"{bucket_name}/{s3_file}"

                # Retrieve the original file name from Elasticsearch metadata
                query = {"query": {"term": {"s3_object_name": s3_object_name}}}
                result = self.es_facade.search(self.index_name, query)

                if result['hits']['total']['value'] > 0:
                    original_file_name = result['hits']['hits'][0]['_source']['metadata'].get('original-file-name',
                                                                                              s3_file)
                else:
                    original_file_name = s3_file  # Fallback to the S3 file name if not found in ES

                files.append({
                    'file_name': original_file_name,
                    's3_object_name': s3_file,
                    'file_size': file_size,  # Size in bytes
                })

            return files
        except Exception as e:
            error_logger.error(f"Failed to list files in bucket '{bucket_name}': {str(e)}")
            raise

    def generate_unique_name(self, object_name):
        """Generate a unique name by appending a UUID to the original name."""
        base_name, extension = object_name.rsplit('.', 1) if '.' in object_name else (object_name, '')
        unique_name = f"{base_name}_{uuid.uuid4().hex}"
        if extension:
            unique_name = f"{unique_name}.{extension}"
        return unique_name

    def update_metadata_field(self, index_name, doc_id, key, value):
        """Update a specific key in the metadata of a document while preserving other metadata fields."""
        try:
            # Retrieve the current document to get the existing metadata
            current_document = self.es_facade.get_document(index_name, doc_id)
            current_metadata = current_document['_source'].get('metadata', {})

            # Update the specific key in the metadata
            current_metadata[key] = value

            # Update the document in Elasticsearch
            update_body = {"metadata": current_metadata}
            self.es_facade.update_document(index_name, doc_id, update_body)

            audit_logger.info(f"Updated metadata '{key}' in document ID '{doc_id}' in index '{index_name}'")
        except Exception as e:
            error_logger.error(
                f"Failed to update metadata '{key}' in document ID '{doc_id}' in index '{index_name}': {str(e)}")
            raise
