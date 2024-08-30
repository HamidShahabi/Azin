import logging

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings

from storage.error_map import ERROR_MAP, DEFAULT_ERROR_MESSAGE

audit_logger = logging.getLogger('audit_logger')
error_logger = logging.getLogger('error_logger')


class S3Facade:
    def __init__(self):
        try:
            self.s3_client = boto3.client(
                's3',
                endpoint_url=settings.S3_ENDPOINT_URL,
                aws_access_key_id=settings.S3_ACCESS_KEY_ID,
                aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
                config=Config(signature_version='s3v4')
            )
            audit_logger.info(f"Initialized S3 client")
        except BotoCoreError as e:
            error_logger.error(f"Failed to initialize S3 client: {str(e)}")
            raise

    @staticmethod
    def get_error_message(error_code):
        """Retrieve error message from error map based on the error code."""
        return ERROR_MAP.get(error_code, DEFAULT_ERROR_MESSAGE)

    def upload_file(self, bucket_name, file_name, object_name=None):
        """Upload a file to the bucket."""
        try:
            if object_name is None:
                object_name = file_name
            self.s3_client.upload_file(file_name, bucket_name, object_name)
            audit_logger.info(f"File uploaded to {bucket_name}/{object_name}")
            return f"{bucket_name}/{object_name}"
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = S3Facade.get_error_message(error_code)
            error_logger.error(f"Failed to upload file {file_name} to bucket {bucket_name}: {error_message} "
                               f"(Error Code: {error_code})")
            raise Exception(f"Failed to upload file '{file_name}' to S3. {error_message}")
        except BotoCoreError as e:
            error_logger.error(f"Failed to upload file {file_name} to bucket {bucket_name}: {str(e)}")
            raise

    def download_file(self, bucket_name, object_name, file_name=None):
        """Download a file from the bucket."""
        try:
            if file_name is None:
                file_name = object_name
            self.s3_client.download_file(bucket_name, object_name, file_name)
            audit_logger.info(f"File downloaded from {bucket_name}/{object_name}")
            return file_name
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = S3Facade.get_error_message(error_code)
            error_logger.error(f"Failed to download file {object_name} from bucket {bucket_name}: {error_message} "
                               f"(Error Code: {error_code})")
            raise Exception(f"Failed to download file '{object_name}' from S3. {error_message}")
        except BotoCoreError as e:
            error_logger.error(f"Failed to download file {object_name} from bucket {bucket_name}: {str(e)}")
            raise

    def list_files(self, bucket_name, prefix=None):
        """List files in the bucket."""
        try:
            kwargs = {'Bucket': bucket_name}
            if prefix:
                kwargs['Prefix'] = prefix

            response = self.s3_client.list_objects_v2(**kwargs)
            file_list = [item['Key'] for item in response.get('Contents', [])]
            audit_logger.info(f"Files listed in bucket {bucket_name} with prefix {prefix}: {file_list}")
            return file_list
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = S3Facade.get_error_message(error_code)
            error_logger.error(
                f"Failed to list files in bucket {bucket_name} with prefix {prefix}: {error_message} "
                f"(Error Code: {error_code})")
            raise Exception(f"Failed to list files in S3 with prefix '{prefix}'. {error_message}")
        except BotoCoreError as e:
            error_logger.error(f"Failed to list files in bucket {bucket_name} with prefix {prefix}: {str(e)}")
            raise

    def delete_file(self, bucket_name, object_name):
        """Delete a file from the bucket."""
        try:
            self.s3_client.delete_object(Bucket=bucket_name, Key=object_name)
            audit_logger.info(f"File {object_name} deleted from bucket {bucket_name}")
            return f"{object_name} deleted."
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = S3Facade.get_error_message(error_code)
            error_logger.error(f"Failed to delete file {object_name} from bucket {bucket_name}: {error_message} "
                               f"(Error Code: {error_code})")
            raise Exception(f"Failed to delete file '{object_name}' from S3. {error_message}")
        except BotoCoreError as e:
            error_logger.error(f"Failed to delete file {object_name} from bucket {bucket_name}: {str(e)}")
            raise

    def generate_presigned_url(self, bucket_name, object_name, expiration=3600):
        """Generate a presigned URL to share an S3 object."""
        try:
            presigned_url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': object_name},
                ExpiresIn=expiration
            )
            audit_logger.info(f"Presigned URL generated for file {object_name} in bucket {bucket_name}")
            return presigned_url
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = S3Facade.get_error_message(error_code)
            error_logger.error(
                f"Failed to generate presigned URL for {object_name} in bucket {bucket_name}: {error_message} "
                f"(Error Code: {error_code})")
            raise Exception(f"Failed to generate presigned URL for '{object_name}'. {error_message}")
        except BotoCoreError as e:
            error_logger.error(
                f"Failed to generate presigned URL for {object_name} in bucket {bucket_name}: {str(e)}")
            raise

    def create_link(self, bucket_name, source_object_name, target_object_name):
        """Create a metadata-based symbolic link (reference) to another file within the same bucket."""
        try:
            # Create the link object with metadata pointing to the original object
            self.s3_client.put_object(
                Bucket=bucket_name,
                Key=target_object_name,
                Metadata={'original-key': source_object_name}
            )
            audit_logger.info(
                f"Metadata-based link created from {source_object_name} to {target_object_name} in bucket {bucket_name}")
            return f"{bucket_name}/{target_object_name}"
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = S3Facade.get_error_message(error_code)
            error_logger.error(
                f"Failed to create metadata link from {source_object_name} to {target_object_name} in bucket {bucket_name}: {error_message} "
                f"(Error Code: {error_code})")
            raise Exception(
                f"Failed to create metadata link from '{source_object_name}' to '{target_object_name}'. {error_message}")
        except BotoCoreError as e:
            error_logger.error(
                f"Failed to create metadata link from {source_object_name} to {target_object_name} in bucket {bucket_name}: {str(e)}")
            raise

    def object_exists(self, bucket_name, object_name):
        """Check if an object with the given name exists in the S3 bucket."""
        try:
            self.s3_client.head_object(Bucket=bucket_name, Key=object_name)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            else:
                raise


    def resolve_link(self, bucket_name, target_object_name):
        """Resolve a metadata-based link to get the original object's key."""
        try:
            response = self.s3_client.head_object(
                Bucket=bucket_name,
                Key=target_object_name
            )
            original_key = response['Metadata'].get('original-key')
            if original_key:
                audit_logger.info(
                    f"Resolved link {target_object_name} to original object {original_key} in bucket {bucket_name}")
                return original_key
            else:
                error_logger.error(f"No link metadata found for {target_object_name} in bucket {bucket_name}")
                return None
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = S3Facade.get_error_message(error_code)
            error_logger.error(
                f"Failed to resolve link {target_object_name} in bucket {bucket_name}: {error_message} "
                f"(Error Code: {error_code})")
            raise Exception(
                f"Failed to resolve link for '{target_object_name}'. {error_message}")
        except BotoCoreError as e:
            error_logger.error(
                f"Failed to resolve link {target_object_name} in bucket {bucket_name}: {str(e)}")
            raise

    def upload_object_body(self, object_name, body, bucket_name=None):
        """Upload an object body to S3."""
        try:
            parts = object_name.split('/')
            bucket_name = parts[0]  # The first part is the bucket name
            file_name = parts[-1]  # The last part is the file name (object name)
            self.s3_client.put_object(Bucket=bucket_name, Key=file_name, Body=body)
            audit_logger.info(f"Uploaded object body to {bucket_name}/{object_name}")
            return f"{bucket_name}/{object_name}"
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = self.get_error_message(error_code)
            error_logger.error(f"Failed to upload object body to {bucket_name}/{object_name}: {error_message} "
                               f"(Error Code: {error_code})")
            raise Exception(f"Failed to upload object body to '{bucket_name}/{object_name}'. {error_message}")
        except BotoCoreError as e:
            error_logger.error(f"Failed to upload object body to {bucket_name}/{object_name}: {str(e)}")
            raise

    def get_object_body(self, object_name, bucket_name=None):
        """Get the body/content of an S3 object."""
        try:
            parts = object_name.split('/')
            bucket_name = parts[0]  # The first part is the bucket name
            file_name = parts[-1]  # The last part is the file name (object name)
            response = self.s3_client.get_object(Bucket=bucket_name, Key=file_name)
            body = response['Body'].read()
            audit_logger.info(f"Retrieved object body from {bucket_name}/{object_name}")
            return body
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = self.get_error_message(error_code)
            error_logger.error(f"Failed to get object body from {bucket_name}/{object_name}: {error_message} "
                               f"(Error Code: {error_code})")
            raise Exception(f"Failed to get object body from '{bucket_name}/{object_name}'. {error_message}")
        except BotoCoreError as e:
            error_logger.error(f"Failed to get object body from {bucket_name}/{object_name}: {str(e)}")
            raise

    def get_object_metadata(self, object_name, bucket_name=None):
        """Retrieve metadata of an S3 object."""
        try:
            bucket_name = bucket_name or self.s3_client.bucket_name
            response = self.s3_client.head_object(Bucket=bucket_name, Key=object_name)
            metadata = response.get('Metadata', {})
            audit_logger.info(f"Retrieved metadata from {bucket_name}/{object_name}")
            return metadata
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = self.get_error_message(error_code)
            error_logger.error(f"Failed to get metadata from {bucket_name}/{object_name}: {error_message} "
                               f"(Error Code: {error_code})")
            raise Exception(f"Failed to get metadata from '{bucket_name}/{object_name}'. {error_message}")
        except BotoCoreError as e:
            error_logger.error(f"Failed to get metadata from {bucket_name}/{object_name}: {str(e)}")
            raise
