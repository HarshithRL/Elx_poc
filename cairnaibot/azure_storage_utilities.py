import io
import os

from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

from config import get_config

load_dotenv()


class AzureStorageUtilities:
    def __init__(self):
        self.config = get_config()

        storage_account_name = self.config["azure"]["storage_account_name"]
        access_key = os.getenv("AZURE_ACCESS_KEY")

        self.blob_service_client = BlobServiceClient(
            account_url=f"https://{storage_account_name}.blob.core.windows.net",
            credential=access_key,
        )

    def read_pdf_from_blob_as_binary(
        self, storage_account_name, container_name, AZURE_ACCESS_KEY, blob_name
    ):
        blob_client = self.blob_service_client.get_blob_client(
            container_name, blob_name
        )

        file_binary = io.BytesIO()
        blob_client.download_blob().download_to_stream(file_binary)

        file_binary.seek(0)

        return file_binary

    def get_cloud_files_meta_data(self):
        container_name = self.config["azure"]["container_name"]
        container_client = self.blob_service_client.get_container_client(container_name)

        blob_list = container_client.list_blobs()
        file_details = []
        for blob in blob_list:
            if blob.name.startswith("pdfs/admin/"):
                file_name = blob.name.replace("pdfs/admin/", "")
                session_id = None
                if "__SESSIONID__" in file_name:
                    file_name, session_id = file_name.split("__SESSIONID__")
                temp_file_details = {
                    "file_name": file_name,
                    "file_last_updated": blob.last_modified.strftime("%d %b %Y"),
                    "session_id" : session_id
                }
                file_details.append(temp_file_details)
        return file_details
