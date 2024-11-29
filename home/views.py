import json
import os
import random
import time
import uuid
from datetime import datetime

from azure.storage.blob import BlobServiceClient
from django.conf import settings
from django.core.files.base import ContentFile
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from dotenv import load_dotenv

from cairnaibot.utils import Utilities
from chat.models import Session
from chat.reader import DocumentReader, ReaderUtils
from config import get_config
from home.forms import CloudFileForm, PDFUploadForm

config = get_config()
utils = Utilities()
reader_utils = ReaderUtils()
load_dotenv()

from django.core.paginator import Paginator

def homepage(request):
    if request.user.is_authenticated:
        user = request.user
        sessions = Session.objects.filter(user=request.user)

        # Get cloud files metadata
        cloud_files_meta_data = utils.azure_utils.get_cloud_files_meta_data()

        # Set up pagination for cloud files (10 files per page)
        paginator = Paginator(cloud_files_meta_data, 10)
        page_number = request.GET.get('page', 1)  # Default to the first page
        cloud_files_page = paginator.get_page(page_number)

        admin_session_exists = utils.check_is_admin_first_session()
        print(admin_session_exists)
        if not admin_session_exists:
            utils.create_new_session(
                session_id="admin_session",
                documents=[],
                user=utils.get_or_create_admin_user(),
                parsed_content=[]
            )
            print("created admin session")
        

        user_sessions_meta_data = [x.meta_data for x in sessions[::-1]]

        context = {
            "username": user.username,
            "user_sessions_meta_data": user_sessions_meta_data,
            "cloud_files_page": cloud_files_page,  # Paginated object
            "is_admin_session": utils.get_or_create_admin_user().id == user.id,
            "form": PDFUploadForm(),
            "cloud_form": CloudFileForm(),
        }
        return render(request, "homepage.html", context)
    else:
        return redirect("login")


def create_session_from_cloud(request):
    if request.method == "POST":
        try:
            # Parse the JSON data
            data = json.loads(request.body)
            selected_files = data.get("files", [])

            # Print the selected files
            print(f"Selected files: {', '.join(selected_files)}")

            original_session = utils.get_session_or_404(
                session_id="admin_session",
                user=utils.get_or_create_admin_user()
            )
            new_session_id = str(uuid.uuid4())

            utils.create_cloud_session(
                original_session=original_session,
                new_session_id=new_session_id,
                new_user=request.user,
                original_file_names_to_keep=selected_files
            )

            # Return a JSON response with the list of selected files
            return JsonResponse({"result": "success", "session_id": new_session_id})
        except json.JSONDecodeError:
            return JsonResponse({"status": "error", "message": "Invalid data."}, status=400)
    else:
        return JsonResponse({"status": "error", "message": "Invalid request method."}, status=405)
    
@require_POST
def process_documents(request):
    """
    Processes uploaded PDF documents by extracting content. Uses OCR if necessary.

    Sample Request:
    POST /process_documents/
    Body:
        {
            "documents": [File objects for documents to process]
        }

    Returns:
        JsonResponse: A JSON response containing parsed content if successful,
                      or an error message if parsing fails.
    """
    form = PDFUploadForm(request.POST, request.FILES)
    if form.is_valid():
        documents = request.FILES.getlist("pdf_file")
        parsed_content = []
        for document in documents:
            file_name = document.name
            file_name = utils.sanitize_filename(file_name)
            content = document.read()

            pages_content = reader_utils.process_document_without_ocr(
                content, file_name
            )
            if pages_content == []:
                pages_content = reader_utils.process_document_with_ocr(
                    content, file_name
                )
                if pages_content != []:
                    parsed_content.extend(pages_content)
            else:
                parsed_content.extend(pages_content)

        if parsed_content != []:
            return JsonResponse(
                {"parsed_content": parsed_content, "error": "None"}, status=200
            )
        else:
            return JsonResponse({"error": "Unable to parse document"}, status=400)
    return JsonResponse({"error": "Invalid form"}, status=400)


@require_POST
def create_session(request):
    """
    Creates a new session for the user with parsed content of uploaded PDF documents.

    Sample Request:
    POST /create_session/
    Body:
        {
            "documents": [File objects for PDFs to upload],
            "parsed_content": JSON string of parsed content from previous processing step
        }

    Returns:
        JsonResponse: A JSON response with a new session ID if successful,
                      or an error message if document content parsing fails.
    """
    form = PDFUploadForm(request.POST, request.FILES)
    if form.is_valid():
        documents = request.FILES.getlist("pdf_file")
        parsed_content = json.loads(request.POST.get("parsed_content", "[]"))
        if parsed_content:
            new_session_id = f"{int(time.time() * 1000)}{random.randint(0, 9999)}"

            utils.create_new_session(
                session_id=new_session_id,
                documents=documents,
                user=request.user,
                parsed_content=parsed_content,
            )

            return JsonResponse(
                {"result": "success", "session_id": new_session_id}, status=200
            )
        else:
            return JsonResponse(
                {"error": "Unable to parse document content"}, status=400
            )
    return JsonResponse({"error": "Invalid form"}, status=400)


@require_POST
def add_to_session(request):
    form = PDFUploadForm(request.POST, request.FILES)
    if form.is_valid():
        documents = request.FILES.getlist("pdf_file")
        parsed_content = json.loads(request.POST.get("parsed_content", "[]"))
        session_id = request.POST.get("session_id")
        print(parsed_content)
        print(session_id)
        print(documents)
        if parsed_content:
            print("here 1")
            utils.add_to_session(
                session_id=session_id,
                documents=documents,
                request=request,
                parsed_content=parsed_content,
            )
            print("added to session")

            return JsonResponse(
                {"result": "success", "session_id": session_id}, status=200
            )
        elif (len(parsed_content)==0) and (request.user == utils.get_or_create_admin_user()):
            print("here 2")
            utils.add_to_session(
                session_id=session_id,
                documents=documents,
                request=request,
                parsed_content=parsed_content,
            )

            return JsonResponse(
                {"result": "success", "session_id": session_id}, status=200
            )
        else:
            print("here 3")
            return JsonResponse(
                {"error": "Unable to parse document content"}, status=400
            )
    return JsonResponse({"error": "Invalid form"}, status=400)


@require_POST
def edit_session_name(request):
    if request.method == "POST":
        data = json.loads(request.body)
        session_id = data.get("session_id")
        session_name = data.get("session_name")

        session = utils.get_session_or_404(session_id, request)
        session.meta_data["session_name"] = session_name
        session.save()
        return redirect("homepage")
    return JsonResponse({"error": "Invalid form"}, status=400)


@require_POST
def delete_session(request):
    """
    Deletes a session identified by the session ID.

    Sample Request:
    POST /delete_session/
    Body:
        {
            "session_id": "unique_session_id_to_delete"
        }

    Returns:
        HttpResponse: Redirects to 'homepage' if successful.
                      Returns a 404 status if the session does not exist.
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            session_id = data.get("session_id")

            session = utils.get_session_or_404(session_id, request)
            session.delete()
            return redirect("homepage")

        except Session.DoesNotExist:
            return HttpResponse("Session does not exist", status=404)