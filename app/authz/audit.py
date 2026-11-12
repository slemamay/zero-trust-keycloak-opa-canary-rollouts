#(wiem)
"""Journal d'audit des décisions d'autorisation (JSON Lines).

Une ligne JSON par décision, écrite sur stdout (docker logs) ET dans
AUTHZ_AUDIT_FILE (par défaut logs/audit.jsonl). Facile à filtrer avec jq.
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone

_logger = logging.getLogger("authz.audit")
_logger.setLevel(logging.INFO)
_logger.propagate = False

if not _logger.handlers:
    _fmt = logging.Formatter("%(message)s")
    _out = logging.StreamHandler(sys.stdout)
    _out.setFormatter(_fmt)
    _logger.addHandler(_out)
    _path = os.getenv("AUTHZ_AUDIT_FILE", "logs/audit.jsonl")
    try:
        os.makedirs(os.path.dirname(_path) or ".", exist_ok=True)
        _file = logging.FileHandler(_path, encoding="utf-8")
        _file.setFormatter(_fmt)
        _logger.addHandler(_file)
    except OSError:
        pass  # le journal stdout reste actif


def log_decision(*, subject, action, resource, context, allow, reasons,
                 path=None, method=None, error=None):
    """Écrit une entrée d'audit. Ne contient jamais le token."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "decision": "ALLOW" if allow else "DENY",
        "user": subject.get("username") or subject.get("sub"),
        "sub_type": subject.get("type"),
        "roles": subject.get("roles"),
        "branch": subject.get("branch"),
        "action": action,
        "resource": {k: resource.get(k) for k in ("type", "id", "branch", "amount")},
        "context": context,
        "reasons": sorted(reasons),
        "http": f"{method} {path}" if path else None,
    }
    if error:
        entry["error"] = error
    _logger.info(json.dumps(entry, ensure_ascii=False, default=str))
    return entry