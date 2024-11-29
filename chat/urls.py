# chat/urls.py
from django.urls import path
from chat import views
from django.views.decorators.csrf import csrf_exempt

urlpatterns = [
    path('test/', views.test, name='test'),
    path('pdf/<str:session_id>/', views.display_pdf, name='display_pdf'),
    path('feedback/', views.feedback_view, name='feedback_view'),
    path('invoke_llm/', views.invoke_llm, name='invoke_llm'),
]
