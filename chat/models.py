import os

from django.contrib.auth.models import User
from django.db import models
from storages.backends.azure_storage import AzureStorage


class MyAzureStorage(AzureStorage):
    azure_container = "cairnpoc2"
    expiration_secs = None


def user_upload_path(instance, filename):
    path = os.path.join("pdfs", instance.user.username, f"{filename}")
    return path


class PDFFile(models.Model):
    file = models.FileField(upload_to=user_upload_path, storage=MyAzureStorage())
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    session = models.ForeignKey(
        "Session", related_name="pdf_files", on_delete=models.CASCADE
    )


class Session(models.Model):
    session_id = models.CharField(max_length=100, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    data = models.JSONField()
    parsed_content = models.JSONField()
    meta_data = models.JSONField()

    open_ai_conversation = models.JSONField(default=list, null=True)
    llama_conversation = models.JSONField(default=list, null=True)
    dbrx_conversation = models.JSONField(default=list, null=True)
    gemini_conversation = models.JSONField(default=list, null=True)

    def __str__(self):
        return self.session_id
