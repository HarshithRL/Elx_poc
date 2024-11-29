import json
import os
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.db import IntegrityError
from django.contrib import messages
from django.contrib.auth import authenticate, login
from dotenv import load_dotenv
from django.shortcuts import redirect, render
from django.shortcuts import get_object_or_404, redirect, render

from cairnaibot.utils import Utilities

from .models import UserProfile

utils = Utilities()

load_dotenv()

@login_required
def settings(request):
    return render(request, "commingsoon.html")


@login_required
def delete_user(request):
    if request.method == "POST":
        user_profile = UserProfile.objects.get(user=request.user)
        user_profile.delete()
        request.user.delete()
        messages.success(request, "Your account has been deleted successfully.")
        return redirect(
            "homepage"
        )  # Redirect to homepage or another page after deletion

    return render(request, "delete_user.html")  # Render a confirmation page


def register(request):
    if request.method == "POST":
        username = request.POST["username"]
        password = request.POST["password"]

        try:
            # Create user
            user = User.objects.create_user(username=username, password=password)

            # Create user profile with an empty conversation
            UserProfile.objects.get_or_create(
                user=user,
                defaults={"conversations": []},
            )

            messages.success(request, "User registered successfully.")
            return redirect("login")
        except IntegrityError:
            messages.error(
                request, "Username already taken. Please choose a different one."
            )
            return redirect("register")

    return render(request, "register.html")


def logout_view(request):
    logout(request)
    next_page = request.GET.get(
        "next", "login"
    )  # Redirect to 'next' if provided, otherwise to 'login'
    return redirect(next_page)

def user_login(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        admin_username = os.getenv("ADMIN_USERNAME")
        admin_password = os.getenv("ADMIN_PASSWORD")
        print(username, type(username), len(username))
        print(admin_username, type(admin_username), len(admin_username))
        print(password, type(password), len(password))
        print(admin_password, type(admin_password), len(admin_password))

        if not username or not password:
            messages.error(request, "Username and password are required.")
            return redirect("login")  # Redirect back to login page

        # Authenticate user
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)  # Log the user in
            return redirect("homepage")  # Redirect to homepage
        else:
            messages.error(request, "Invalid username or password.")  # Error message
            print("Invalid username or password.")
            return redirect("login")  # Redirect back to login page

    return render(request, "login.html")

