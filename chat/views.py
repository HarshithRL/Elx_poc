import base64
import json

from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt

from cairnaibot.utils import Utilities
from home.forms import CloudFileForm, PDFUploadForm
from user_login.models import UserProfile

from .models import Session

utils = Utilities()


def test(request):
    session_id = "17308022124624595"
    session = utils.get_session_or_404(session_id, request)
    user = request.user
    profile, created = UserProfile.objects.get_or_create(user=user)

    context = {
        "pdf_uploads": session.pdf_files.all(),
        "profile": profile,
        "created": created,
        "user_name": user.username,
        "previous_conversations": session.data,
        "session_id": session_id,
        "last_message_index": len(session.data),
    }

    return render(request, "test.html", context)


def display_pdf(request, session_id):
    """
    Displays the PDF files associated with a specific session, along with user profile information
    and previous conversation history.

    Sample Request:
    GET /display_pdf/{session_id}/
    No request body parameters required.

    Parameters:
        request (HttpRequest): The HTTP request object.
        session_id (str): The ID of the session to display.

    Returns:
        HttpResponse: Renders the 'display_pdf.html' template with session details, PDF files,
                      user profile, and previous conversations.
    """
    session = utils.get_session_or_404(session_id, request)
    user = request.user
    profile, created = UserProfile.objects.get_or_create(user=user)
    previous_conversations = session.data

    # Convert to JSON, encode to bytes, then encode in base64
    previous_conversations_json = json.dumps(previous_conversations)
    previous_conversations_base64 = base64.b64encode(
        previous_conversations_json.encode("utf-8")
    ).decode("utf-8")

    context = {
        "pdf_uploads": session.pdf_files.all(),
        "profile": profile,
        "created": created,
        "user_name": user.username,
        "previous_conversations": previous_conversations_base64,
        "session_id": session_id,
        "flow_index": 0,
        "conversation_index": len(session.data[0]),
        "form": PDFUploadForm(),
    }

    return render(request, "display_pdf.html", context)


def invoke_llm(request):
    """
    Invokes a language model (LLM) based on user input, relevant content, and previous conversation history.

    Sample Request:
    POST /invoke_llm/
    Body:
        {
            "session_id": "osdaubn012hn31ou3hr01",
            "llm_name": "openai",
            "user_input": "Write an email explain gen AI use cases",
            "relavant_content": "This is a sample relavant content",
            "conversation_index": 5
        }

    Parameters:
        request (HttpRequest): The HTTP request object.

    Returns:
        StreamingHttpResponse: A streaming HTTP response containing the LLM's output in a text/event-stream format,
                               or a JSON response with an error if the request is invalid.
    """
    if request.method == "POST":
        data = json.loads(request.body)

        session_id = data.get("session_id")
        llm_name = data.get("llm_name")
        user_input = data.get("user_input")
        flow_index = data.get("flow_index")
        conversation_index = data.get("conversation_index")

        session = utils.get_session_or_404(session_id, request)
        retreived_content = utils.get_retreiver_response(
            request.user.id, session, session_id, user_input
        )

        relavant_content = [
            x.text
            + f"\n\nFile name: {x.metadata['file_name']}"
            + f"\n\nPage number: {x.metadata['page_number']}\n\n\n\n"
            for x in retreived_content
        ]

        session.save()

        user_request = utils.get_user_request(relavant_content, user_input, llm_name)

        previous_conversations = utils.get_previous_conversations(
            session.data[flow_index][:conversation_index], llm_name
        )

        data = session.data
        data[flow_index].append({"user_input": user_input})
        session.data = data
        session.save()

        llm_input = previous_conversations + [user_request]
        llm_output = utils.get_llm_output(session, flow_index, llm_input, llm_name)

        return StreamingHttpResponse(llm_output, content_type="text/event-stream")

    return JsonResponse({"error": "Invalid request"}, status=400)


@csrf_exempt
def feedback_view(request):
    """
    Submits user feedback on a specific conversation with a language model (LLM).

    Sample Request:
    POST /feedback_view/
    Body:
        {
            "model": "openai",
            "conversation_index": 12,
            "session_id": "2346b2356brjerth",
            "feedback": "Good"
        }

    Parameters:
        request (HttpRequest): The HTTP request object.

    Returns:
        JsonResponse: A JSON response indicating success if feedback is saved,
                      or an error message if the request is invalid.
    """
    if request.method == "POST":
        data = json.loads(request.body)

        llm_name = data.get("model")
        conversation_index = data.get("conversation_index")
        session_id = data.get("session_id")
        feedback = data.get("feedback")

        session = get_object_or_404(Session, session_id=session_id)

        if llm_name.startswith("open_ai"):
            session.data[conversation_index]["open_ai_feedback"] = feedback

        elif llm_name.startswith("llama"):
            session.data[conversation_index]["llama_feedback"] = feedback

        elif llm_name.startswith("dbrx"):
            session.data[conversation_index]["dbrx_feedback"] = feedback

        elif llm_name.startswith("gemini"):
            session.data[conversation_index]["gemini_feedback"] = feedback

        session.save()

        return JsonResponse({"status": "success"}, status=200)

    return JsonResponse({"error": "Invalid request"}, status=400)
