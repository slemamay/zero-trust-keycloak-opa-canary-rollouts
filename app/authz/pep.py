#wiem
"""Cœur du PEP (Policy Enforcement Point) : sans dépendance Django.

Construit l'input OPA {subject, resource, action, context}, interroge le PDP
(POST /v1/data/enterprise/authz/decision) et applique le principe fail-closed :
toute erreur ou réponse inattendue => refus.
"""
import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

OPA_URL = os.getenv("OPA_URL", "http://localhost:8181")
OPA_DECISION_PATH = os.getenv("OPA_DECISION_PATH", "/v1/data/enterprise/authz/decision")
OPA_TIMEOUT = float(os.getenv("OPA_TIMEOUT", "2"))
TZ = ZoneInfo(os.getenv("AUTHZ_TZ", "Africa/Tunis"))


def build_subject(identity: dict) -> dict:
    """identity = sortie de authn.jwks.extract_identity().

    - type : 'agent' si le token ne porte que des agent_scopes (agent IA
      délégué), sinon 'human'.
    - sub  : on envoie le username, car banking.Transaction.created_by stocke
      le username ; sans ça la règle « pas d'auto-approbation » ne marcherait pas.
    """
    roles = identity.get("roles") or []
    scopes = identity.get("agent_scopes") or []
    is_agent = bool(scopes) and not roles
    return {
        "sub": identity.get("username") or identity["sub"],
        "kc_sub": identity["sub"],
        "username": identity.get("username"),
        "type": "agent" if is_agent else "human",
        "roles": roles,
        "branch": identity.get("branch"),
        "agent_scopes": scopes,
    }


def build_context(now=None) -> dict:
    """Heure et jour en heure locale (Africa/Tunis).

    AUTHZ_FAKE_NOW (ex. 2026-11-14T22:00) sert UNIQUEMENT aux démos
    (simuler la nuit ou le week-end).
    """
    if now is None:
        fake = os.getenv("AUTHZ_FAKE_NOW")
        now = datetime.fromisoformat(fake) if fake else datetime.now(TZ)
    return {"hour": now.hour, "weekday": now.strftime("%A")}


def build_resource(transaction) -> dict:
    return {
        "type": "transaction",
        "id": str(transaction.pk),
        "branch": transaction.branch.code,
        "amount": float(transaction.amount),
        "created_by": transaction.created_by,
    }


def decide(subject: dict, action: str, resource: dict, context: dict | None = None):
    """Retourne (allow: bool, reasons: list[str], context: dict, error: str|None)."""
    context = context or build_context()
    payload = json.dumps({"input": {
        "subject": subject, "resource": resource,
        "action": action, "context": context,
    }}).encode()
    req = urllib.request.Request(
        OPA_URL + OPA_DECISION_PATH, data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=OPA_TIMEOUT) as resp:
            result = json.loads(resp.read()).get("result")
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        return False, ["pdp_unavailable"], context, f"{type(exc).__name__}: {exc}"

    if not isinstance(result, dict) or result.get("allow") is not True:
        reasons = result.get("reasons", []) if isinstance(result, dict) else []
        return False, list(reasons) or ["denied_by_policy"], context, None
    return True, [], context, None