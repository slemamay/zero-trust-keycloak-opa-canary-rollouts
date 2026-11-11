# Policies (OPA / Rego)

Hybrid RBAC + ABAC authorization for the banking platform.

## Files
- `authz.rego`: entry point (`enterprise.authz.allow` and `decision`)
- `roles.rego`: RBAC (role to actions)
- `abac.rego`: ABAC (branch, amount, business hours, separation of duties, AI agent scopes)
- `data.json`: editable thresholds, hours and role permissions
- `authz_test.rego`: unit tests

## Run the tests (PowerShell)
    docker run --rm -v "${PWD}/policies:/policies" openpolicyagent/opa test /policies -v

## Run OPA as a server
    docker run --rm -p 8181:8181 -v "${PWD}/policies:/policies" openpolicyagent/opa run --server --watch --addr 0.0.0.0:8181 /policies

## Endpoints
- `POST /v1/data/enterprise/authz/allow` returns `{"result": true|false}`
- `POST /v1/data/enterprise/authz/decision` returns allow plus reasons (audit log)

## Hot-swap demo
Edit `amount_limits.manager` in `data.json` (50000 to 10000), reload OPA,
and the same request is now denied. No Django code is changed or redeployed.

## Input contract
subject (sub, type, roles, branch, agent_scopes), resource (type, id, branch, amount, created_by),
action (view, create, approve, view_audit), context (hour, weekday).