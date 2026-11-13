"""PolicyEnforcementMiddleware : le PEP de Django.

Pour chaque vue protégée : 1) vérifie le JWT (JWKS), 2) construit l'input,
3) demande la décision à OPA (PDP), 4) journalise, 5) laisse passer ou 403.
Fail-closed : vue non déclarée => refus ; OPA injoignable => 503.
"""
from django.http import JsonResponse

from authn.jwks import extract_identity, verify_token
from banking.models import Transaction

from . import audit, pep

# nom de la vue -> (action, type de ressource). Toute autre vue est refusée,
# sauf celles listées dans AUTHENTICATED_ONLY.
PROTECTED = {
    "transaction_approve": ("approve", "transaction"),
}
# JWT valide suffit ; la liste est filtrée ligne par ligne via OPA dans la vue
AUTHENTICATED_ONLY = {"whoami", "transactions_list"}
SKIP_PREFIXES = ("/admin/", "/oidc/", "/static/")


class PolicyEnforcementMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.path.startswith(SKIP_PREFIXES):
            return None

        name = getattr(view_func, "__name__", "")

        # --- AuthN : JWT stateless ---
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return JsonResponse({"error": "non authentifié"}, status=401)
        try:
            identity = extract_identity(verify_token(auth[7:]))
        except Exception:
            return JsonResponse({"error": "token invalide"}, status=401)

        subject = pep.build_subject(identity)
        request.identity = identity

        if name in AUTHENTICATED_ONLY:
            return None

        # --- AuthZ : décision OPA ---
        if name not in PROTECTED:
            audit.log_decision(subject=subject, action=name, resource={}, context={},
                               allow=False, reasons=["vue non déclarée (deny by default)"],
                               path=request.path, method=request.method)
            return JsonResponse({"error": "interdit"}, status=403)

        action, _rtype = PROTECTED[name]
        try:
            tx = Transaction.objects.select_related("branch").get(pk=view_kwargs["pk"])
        except Transaction.DoesNotExist:
            return JsonResponse({"error": "introuvable"}, status=404)

        resource = pep.build_resource(tx)
        allow, reasons, ctx, error = pep.decide(subject, action, resource)
        audit.log_decision(subject=subject, action=action, resource=resource,
                           context=ctx, allow=allow, reasons=reasons,
                           path=request.path, method=request.method, error=error)
        if allow:
            return None
        status = 503 if error else 403
        return JsonResponse({"error": "interdit", "reasons": reasons}, status=status)