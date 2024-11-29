from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('delete/', views.delete_user, name='delete_user'),
    path('settings/', views.settings, name='settings'),
]
