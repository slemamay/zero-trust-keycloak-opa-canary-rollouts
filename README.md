# Project 44 - Zero-Trust Identity (Keycloak OIDC) + Policy-as-Code (OPA/Rego)

## Run
    cp .env.example .env
    docker compose down            # important if an old Keycloak container exists
    docker compose up -d           # Keycloak :8080, OPA :8181, PostgreSQL :5432
    cd app
    pipenv install && pipenv shell     # or: pip install django mozilla-django-oidc "PyJWT[crypto]" requests psycopg2-binary tzdata
    python manage.py migrate
    python manage.py loaddata banking/fixtures/seed.json
    python manage.py runserver         # Django :8000 (runs on the host, not in Docker)

Keycloak admin: http://localhost:8080 (admin / admin). The realm `projet44` is imported automatically.

## Test users (realm projet44)
| User | Password | Role | Branch | Notes |
|---|---|---|---|---|
| alice | Alice123! | caissier | AG01 | |
| bob | Bob123! | manager | AG01 | approves up to 50 000 |
| carla | Carla123! | auditeur | (all) | view only |
| agent-ia | Agent123! | none (delegated agent) | AG01 | scopes: transactions:read, transactions:draft |

OIDC client: `django-app`, secret `projet44-dev-secret` (dev only), PKCE S256.
Direct Access Grant is enabled only so `scripts/demo.sh` can fetch tokens with curl.

## Tests
    docker run --rm -v "${PWD}/policies:/policies" openpolicyagent/opa:1.4.2 test /policies -v
    cd app && python -m unittest authz.tests && python manage.py test authn banking

## Demo
See `scripts/demo.sh` and `scripts/hot_swap_demo.md`. Policies are in `policies/` (OPA reloads on save, no Django restart).
