"""URL routes for the Django deployment skeleton."""

from django.http import JsonResponse
from django.urls import path
from .views import evaluate


def health(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("api/evaluate/", evaluate, name="evaluate"),
    path("health/", health, name="health"),
]
