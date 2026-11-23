from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from authz import audit, pep
from .models import Branch, Transaction


# L'authentification (401) et l'autorisation (403) de l'approbation sont gérées
# par authz.middleware.PolicyEnforcementMiddleware : plus aucun if role == ... ici.

def transactions_list(request):
    """Liste filtrée : on ne renvoie que ce qu'OPA autorise en 'view'."""
    subject = pep.build_subject(request.identity)
    ctx = pep.build_context()
    visible = []
    for t in Transaction.objects.select_related("branch"):
        resource = pep.build_resource(t)
        allow, reasons, _, error = pep.decide(subject, "view", resource, ctx)
        audit.log_decision(subject=subject, action="view", resource=resource,
                           context=ctx, allow=allow, reasons=reasons,
                           path=request.path, method=request.method, error=error)
        if error:  # PDP injoignable : fail-closed, pas de liste vide trompeuse
            return JsonResponse({"error": "interdit", "reasons": reasons}, status=503)
        if allow:
            visible.append({"id": t.id, "amount": str(t.amount), "status": t.status,
                            "branch__code": t.branch.code, "created_by": t.created_by})
    return JsonResponse(visible, safe=False)


@csrf_exempt
@require_http_methods(["POST"])
def transaction_create(request):
    """Création d'une opération (PENDING). Corps JSON : {branch?, amount, description?}.

    Le PEP a déjà validé le corps et obtenu l'accord d'OPA (rôle, agence,
    plafond, heures ouvrables, scope de l'agent IA) : request.tx_payload est fiable.
    """
    p = request.tx_payload
    t = Transaction.objects.create(
        branch=Branch.objects.get(code=p["branch"]),
        created_by=request.identity.get("username") or request.identity["sub"],
        amount=p["amount"], description=p["description"],
    )
    return JsonResponse({"ok": True, "id": t.id, "status": t.status,
                         "branch": p["branch"], "amount": str(t.amount)}, status=201)


@csrf_exempt
@require_http_methods(["POST"])
def transaction_approve(request, pk):
    t = Transaction.objects.get(pk=pk)   # existence déjà vérifiée par le PEP
    t.status = "APPROVED"
    t.approved_by = request.identity["username"]
    t.save()
    return JsonResponse({"ok": True, "id": t.id, "approved_by": t.approved_by})


def whoami(request):
    return JsonResponse(request.identity)