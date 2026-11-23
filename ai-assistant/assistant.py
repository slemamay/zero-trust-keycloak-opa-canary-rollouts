#!/usr/bin/env python3
"""AI policy assistant: compliance requirement (plain text) -> candidate Rego -> deterministic gate.

Usage:
  Any OpenAI-compatible LLM, configured with LLM_BASE_URL / LLM_MODEL / LLM_API_KEY (see llm.py), e.g. local Ollama (default):
  python ai-assistant/assistant.py "Block approvals above 30000 TND on Friday after 14:00"        # real LLM
  python ai-assistant/assistant.py "<requirement>" --provider mock                                  # offline demo
"""
import argparse
import json
import os
import re
import sys
import urllib.error
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate  # noqa: E402
import llm  # noqa: E402

SYSTEM = """You are a Rego (OPA 1.x) policy engineer for a banking platform.
Turn the compliance requirement into a CANDIDATE rule plus unit tests.

Input document available to rules (and to tests via `with input as`):
  input.subject  = {sub, type: "human"|"agent", roles: [...], branch, agent_scopes: [...]}
  input.resource = {type: "transaction", id, branch, amount (TND), created_by}
  input.action   = "view" | "create" | "approve" | "view_audit"
  input.context  = {hour: 0-23 (Africa/Tunis), weekday: "Monday".."Sunday" (English, capitalised)}

STRICT FORMAT RULES
1. Rule file: `package enterprise.candidates.<snake_name>`, then `import rego.v1`.
2. The rule file defines ONLY a set `violation`: `violation contains "<message>" if { ... }`.
   A request is denied when `violation` is non-empty. Never define `allow` or `default`.
3. Test file: `package enterprise.candidates_test.<same snake_name>`, `import rego.v1`,
   `import data.enterprise.candidates.<snake_name> as rule`. At least 4 tests named `test_...`,
   covering: a violating case, the exact threshold boundary, a non-violating case, another action.
   Use `with input as {...}` and `rule.violation`.
4. No http.send, no net.*, no external data. Use tabs for indentation.
5. Reply with exactly two fenced code blocks: first ```rego (rule), second ```rego (tests). No prose.
"""


def extract_blocks(text):
    blocks = re.findall(r"```(?:rego)?\s*\n(.*?)```", text, re.S)
    if len(blocks) < 2:
        return None, None
    return blocks[0].strip() + "\n", blocks[1].strip() + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("requirement")
    ap.add_argument("--provider", default="openai", choices=["openai", "mock"], help="openai = any OpenAI-compatible API (LLM_BASE_URL), mock = canned drafts, no network")
    ap.add_argument("--model", default=None, help="default: $LLM_MODEL or " + llm.DEFAULT_MODEL)
    ap.add_argument("--max-attempts", type=int, default=3)
    ap.add_argument("--mock-script", default=None, help="e.g. draft_1_rejected,draft_2_accepted")
    ap.add_argument("--dry-run", action="store_true", help="validate but do not install the rule")
    a = ap.parse_args()

    model = a.model or os.environ.get("LLM_MODEL") or llm.DEFAULT_MODEL
    chat = llm.get_client(a.provider, a.mock_script)
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Compliance requirement:\n{a.requirement}"}]
    log = {"ts": datetime.now().isoformat(timespec="seconds"), "requirement": a.requirement,
           "provider": a.provider, "model": model,
           "endpoint": None if a.provider == "mock" else os.environ.get("LLM_BASE_URL", llm.DEFAULT_BASE), "attempts": []}
    accepted = None

    for n in range(1, a.max_attempts + 1):
        print(f"\n=== Attempt {n}/{a.max_attempts}: asking {a.provider} ===")
        try:
            reply = chat(msgs, model)
        except Exception as e:  # message clair au lieu d'une trace de 40 lignes
            print(f"\nERREUR : le fournisseur '{a.provider}' n'a pas répondu ({type(e).__name__}).")
            if isinstance(e, KeyError) and "LLM_API_KEY" in str(e):
                print("-> La variable LLM_API_KEY n'est pas définie dans ce terminal.")
            elif isinstance(e, urllib.error.HTTPError):
                body = e.read().decode("utf-8", "replace")[:300]
                print(f"-> HTTP {e.code} : {body}")
                print("-> 400/403 : clé invalide. 404 : nom de modèle ou URL incorrect. 429/503 : service saturé, réessayer ou changer de modèle.")
            elif isinstance(e, urllib.error.URLError):
                print("-> Pas de connexion à l'API. Vérifiez Internet, ou utilisez --provider mock (démo hors ligne).")
            else:
                print(f"-> {e}")
            sys.exit(2)
        rule, tests = extract_blocks(reply)
        if rule is None:
            report, res = "[FAIL] parse: expected two fenced code blocks (rule, tests)", None
        else:
            res = gate.run_gate(rule, tests)
            report = res.report()
        print(report)
        log["attempts"].append({"n": n, "reply": reply, "gate": report,
                                "accepted": bool(res and res.accepted)})
        if res and res.accepted:
            accepted = res
            break
        print("-> REJECTED by the deterministic gate; sending the errors back to the LLM.")
        msgs += [{"role": "assistant", "content": reply},
                 {"role": "user", "content": "The OPA gate rejected your draft:\n" + report +
                  "\nFix it and reply again with the two complete code blocks only."}]

    if accepted:
        if a.dry_run:
            print(f"\nACCEPTED (dry-run) rule '{accepted.name}'. Nothing written.")
        else:
            path = gate.install(accepted)
            print(f"\nACCEPTED: rule '{accepted.name}' written to {path}")
            print("OPA (--watch) hot-loads it; no Django restart needed.")
        log["accepted_rule"] = accepted.name
    else:
        print("\nNO rule accepted. Nothing was written to policies/.")
    runs = Path(__file__).resolve().parent / "runs"
    runs.mkdir(exist_ok=True)
    (runs / f"run-{datetime.now():%Y%m%d-%H%M%S}.json").write_text(
        json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    sys.exit(0 if accepted else 1)


if __name__ == "__main__":
    main()
