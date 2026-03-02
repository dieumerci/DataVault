
from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "ui"

urlpatterns = [
    path("", views.index, name="index"),

    path("upload/", views.upload, name="upload"),
    path("documents/<uuid:pk>/", views.document_detail, name="document_detail"),

    path("fields/<int:pk>/correct/", views.correct_field, name="correct_field"),

    path("search/", views.search, name="search"),

    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
