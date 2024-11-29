from django.conf import settings
from django.conf.urls.static import static
from django.urls import path

from home import views

urlpatterns = [
    path("", views.homepage, name="homepage"),
    path("process_documents/", views.process_documents, name="processDocuments"),
    path("create_session/", views.create_session, name="createSession"),
    path("delete_session/", views.delete_session, name="deleteSession"),
    path("edit_session_name/", views.edit_session_name, name="editSessionName"),
    path("add_to_session/", views.add_to_session, name="addToSession"),
    path('create-session-from-cloud/', views.create_session_from_cloud, name='create_session_from_cloud'),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
