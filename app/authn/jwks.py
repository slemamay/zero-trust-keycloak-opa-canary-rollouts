import os
import jwt
from jwt import PyJWKClient

PUBLIC_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8080")
INTERNAL_URL = os.getenv("KEYCLOAK_INTERNAL_URL", PUBLIC_URL)
REALM = os.getenv("KEYCLOAK_REALM", "projet44")
CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "django-app")

ISSUER = f"{PUBLIC_URL}/realms/{REALM}"
JWKS_URL = f"{INTERNAL_URL}/realms/{REALM}/protocol/openid-connect/certs"

_jwks = PyJWKClient(JWKS_URL, cache_keys=True)
BUSINESS_ROLES = {"caissier", "manager", "auditeur"}

def verify_token(token: str) -> dict:
    key = _jwks.get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token, key.key,
        algorithms=["RS256"],
        issuer=ISSUER,
        options={"require": ["exp", "iss"], "verify_aud": False},
    )
    aud = claims.get("aud", [])
    aud = [aud] if isinstance(aud, str) else aud
    if CLIENT_ID not in aud and claims.get("azp") != CLIENT_ID:
        raise jwt.InvalidAudienceError("token non destiné à django-app")
    return claims

def extract_identity(claims: dict) -> dict:
    """Le 'subject' que le PEP (M4) enverra à OPA."""
    scopes = claims.get("agent_scopes", [])
    return {
        "sub": claims["sub"],
        "username": claims.get("preferred_username"),
        "roles": [r for r in claims.get("realm_access", {}).get("roles", [])
                  if r in BUSINESS_ROLES],
        "branch": claims.get("agence"),
        "agent_scopes": [scopes] if isinstance(scopes, str) else scopes,
    }