package enterprise.authz_test

import data.enterprise.authz
import rego.v1

cashier := {"sub": "u-cashier", "type": "human", "roles": ["caissier"], "branch": "tunis"}

manager := {"sub": "u-manager", "type": "human", "roles": ["manager"], "branch": "tunis"}

auditor := {"sub": "u-audit", "type": "human", "roles": ["auditeur"], "branch": "sfax"}

agent := {
	"sub": "agent-1", "type": "agent", "roles": [],
	"branch": "tunis", "agent_scopes": ["transactions:read", "transactions:draft"],
}

day := {"hour": 10, "weekday": "Tuesday"}

night := {"hour": 22, "weekday": "Tuesday"}

weekend := {"hour": 10, "weekday": "Sunday"}

txn(branch, amount) := {
	"type": "transaction", "id": "t1",
	"branch": branch, "amount": amount, "created_by": "u-other",
}

# ---------- RBAC ----------
test_cashier_can_create_small if authz.allow with input as {"subject": cashier, "resource": txn("tunis", 500), "action": "create", "context": day}

test_cashier_cannot_approve if not authz.allow with input as {"subject": cashier, "resource": txn("tunis", 500), "action": "approve", "context": day}

test_cashier_can_view_large if authz.allow with input as {"subject": cashier, "resource": txn("tunis", 9000), "action": "view", "context": day}

test_manager_can_approve if authz.allow with input as {"subject": manager, "resource": txn("tunis", 20000), "action": "approve", "context": day}

# ---------- ABAC: amount ----------
test_cashier_over_limit_denied if not authz.allow with input as {"subject": cashier, "resource": txn("tunis", 1500), "action": "create", "context": day}

test_manager_over_limit_denied if not authz.allow with input as {"subject": manager, "resource": txn("tunis", 60000), "action": "approve", "context": day}

# ---------- ABAC: branch ----------
test_manager_other_branch_denied if not authz.allow with input as {"subject": manager, "resource": txn("sfax", 100), "action": "approve", "context": day}

test_auditor_views_any_branch if authz.allow with input as {"subject": auditor, "resource": txn("tunis", 100), "action": "view", "context": day}

test_auditor_cannot_approve if not authz.allow with input as {"subject": auditor, "resource": txn("sfax", 100), "action": "approve", "context": day}

# ---------- ABAC: business hours ----------
test_approve_at_night_denied if not authz.allow with input as {"subject": manager, "resource": txn("tunis", 100), "action": "approve", "context": night}

test_approve_on_weekend_denied if not authz.allow with input as {"subject": manager, "resource": txn("tunis", 100), "action": "approve", "context": weekend}

test_view_at_night_allowed if authz.allow with input as {"subject": manager, "resource": txn("tunis", 100), "action": "view", "context": night}

# ---------- Separation of duties ----------
test_self_approval_denied if not authz.allow with input as {
	"subject": manager,
	"resource": object.union(txn("tunis", 100), {"created_by": "u-manager"}),
	"action": "approve",
	"context": day,
}

# ---------- AI agent ----------
test_agent_can_draft_small if authz.allow with input as {"subject": agent, "resource": txn("tunis", 200), "action": "create", "context": day}

test_agent_cannot_approve if not authz.allow with input as {"subject": agent, "resource": txn("tunis", 200), "action": "approve", "context": day}

test_agent_over_cap_denied if not authz.allow with input as {"subject": agent, "resource": txn("tunis", 900), "action": "create", "context": day}

# ---------- Fail-closed ----------
test_empty_input_denied if not authz.allow with input as {}

test_reasons_on_branch_mismatch if "branch mismatch" in authz.reasons with input as {"subject": manager, "resource": txn("sfax", 100), "action": "view", "context": day}
