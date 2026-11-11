package enterprise.authz.roles

import rego.v1

# Every action granted through any of the subject's roles (set = merged, no duplicates)
granted_actions contains action if {
	some role in input.subject.roles
	some action in data.config.role_permissions[role]
}

role_allows if input.action in granted_actions
