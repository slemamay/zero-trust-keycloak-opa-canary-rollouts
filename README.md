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

## API
| Method | Path | Authorization |
|---|---|---|
| GET | `/whoami/` | valid JWT |
| GET | `/transactions/` | valid JWT; rows filtered one by one through OPA (`view`); 503 if OPA is down |
| POST | `/transactions/create/` | OPA `create` (role, branch, amount limit, business hours, agent `transactions:draft` scope). Body: `{"branch": "AG01", "amount": 500, "description": "..."}` (`branch` defaults to the token's branch) |
| POST | `/transactions/<id>/approve/` | OPA `approve` (adds: not your own transaction) |

## Benchmark
    python scripts/benchmark_pep.py            # PEP -> OPA, 100 requests (allow + deny)
    python scripts/benchmark_pep.py --e2e      # + HTTP through Django (Keycloak and Django must be running)
Results are printed as a table and saved in `docs/benchmark.json`.

## Demo
See `scripts/demo.sh` and `scripts/hot_swap_demo.md`. Policies are in `policies/` (OPA reloads on save, no Django restart).
