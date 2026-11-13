from django.urls import path
from . import views

urlpatterns = [
    path("transactions/", views.transactions_list),
    path("transactions/<int:pk>/approve/", views.transaction_approve),
    path("whoami/", views.whoami),
]