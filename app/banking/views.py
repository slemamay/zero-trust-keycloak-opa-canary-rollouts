from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from authn.jwks import verify_token, extract_identity
from .models import Transaction

def _identity(request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        return extract_identity(verify_token(auth[7:]))
    except Exception:
        return None

def transactions_list(request):
    who = _identity(request)
    if not who:
        return JsonResponse({"error": "non authentifié"}, status=401)
    qs = Transaction.objects.values("id", "amount", "status", "branch__code", "created_by")
    return JsonResponse(list(qs), safe=False)

@csrf_exempt
@require_http_methods(["POST"])
def transaction_approve(request, pk):
    who = _identity(request)
    if not who:
        return JsonResponse({"error": "non authentifié"}, status=401)
    # L'autorisation (403) sera ajoutée par le middleware PEP (authz/, M4)
    try:
        t = Transaction.objects.get(pk=pk)
    except Transaction.DoesNotExist:
        return JsonResponse({"error": "introuvable"}, status=404)
    t.status = "APPROVED"
    t.approved_by = who["username"]
    t.save()
    return JsonResponse({"ok": True, "id": t.id, "approved_by": t.approved_by})

def whoami(request):
    who = _identity(request)
    if not who:
        return JsonResponse({"error": "non authentifié"}, status=401)
    return JsonResponse(who)