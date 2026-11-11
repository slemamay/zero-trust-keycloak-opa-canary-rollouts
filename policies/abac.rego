package enterprise.authz.abac

import rego.v1

is_agent if input.subject.type == "agent"

# ---- Branch: same branch, or a global role (auditeur) ----
branch_match if input.subject.branch == input.resource.branch

branch_match if {
	some role in input.subject.roles
	role in data.config.global_branch_roles
}

# ---- Amount limit (applies to create/approve only) ----
amount_limit := data.config.agent_max_amount if is_agent

amount_limit := max({l |
	some role in input.subject.roles
	l := data.config.amount_limits[role]
}) if not is_agent

amount_ok if not input.action in data.config.amount_restricted_actions

amount_ok if input.resource.amount <= amount_limit

# ---- Business hours (restricted actions only) ----
hours_ok if not input.action in data.config.business_hours.restricted_actions

hours_ok if {
	input.context.hour >= data.config.business_hours.start
	input.context.hour < data.config.business_hours.end
	input.context.weekday in data.config.business_hours.days
}

# ---- Separation of duties: nobody approves their own transaction ----
not_self_approval if input.action != "approve"

not_self_approval if input.resource.created_by != input.subject.sub

# ---- AI agent delegated scopes ----
agent_actions contains action if {
	some scope in input.subject.agent_scopes
	some action in data.config.agent_scope_actions[scope]
}

agent_scope_allows if input.action in agent_actions
