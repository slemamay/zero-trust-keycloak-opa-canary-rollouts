package enterprise.authz

import data.enterprise.authz.abac
import data.enterprise.authz.roles
import rego.v1

# Zero trust: deny unless explicitly allowed
default allow := false

permitted if {
	not abac.is_agent
	roles.role_allows
}

permitted if {
	abac.is_agent
	abac.agent_scope_allows
}

allow if {
	permitted
	abac.branch_match
	abac.amount_ok
	abac.hours_ok
	abac.not_self_approval
}

# Human-readable reasons for the audit log (Member 4)
reasons contains "action not permitted for this role/agent scope" if not permitted

reasons contains "branch mismatch" if not abac.branch_match

reasons contains "amount above allowed limit" if not abac.amount_ok

reasons contains "outside business hours" if not abac.hours_ok

reasons contains "cannot approve own transaction" if not abac.not_self_approval

decision := {"allow": allow, "reasons": reasons}
