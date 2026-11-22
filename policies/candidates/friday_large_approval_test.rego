package enterprise.candidates_test.friday_large_approval

import data.enterprise.candidates.friday_large_approval as rule
import rego.v1

base := {
	"action": "approve",
	"resource": {"amount": 40000},
	"context": {"weekday": "Friday", "hour": 15},
}

test_blocks_large_friday_afternoon if {
	"large approval blocked on Friday afternoon" in rule.violation with input as base
}

test_allows_exact_threshold if {
	count(rule.violation) == 0 with input as object.union(base, {"resource": {"amount": 30000}})
}

test_allows_friday_morning if {
	count(rule.violation) == 0 with input as object.union(base, {"context": {"weekday": "Friday", "hour": 10}})
}

test_allows_other_weekday if {
	count(rule.violation) == 0 with input as object.union(base, {"context": {"weekday": "Tuesday", "hour": 15}})
}

test_ignores_view_action if {
	count(rule.violation) == 0 with input as object.union(base, {"action": "view"})
}
