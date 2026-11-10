from django.db import models
from django.utils import timezone

class Branch(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100)
    def __str__(self): return f"{self.code} - {self.name}"

class Transaction(models.Model):
    STATUS = [("PENDING", "En attente"), ("APPROVED", "Approuvée"), ("REJECTED", "Refusée")]
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    created_by = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="PENDING")
    approved_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
