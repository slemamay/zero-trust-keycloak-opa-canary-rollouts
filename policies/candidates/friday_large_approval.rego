package enterprise.candidates.friday_large_approval

import rego.v1

# Compliance: approvals above 30 000 TND are blocked on Friday from 14:00.
violation contains "large approval blocked on Friday afternoon" if {
	input.action == "approve"
	input.resource.amount > 30000
	input.context.weekday == "Friday"
	input.context.hour >= 14
}
