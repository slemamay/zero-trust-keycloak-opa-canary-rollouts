"""Deterministic acceptance gate for AI-drafted Rego rules.

The LLM is never trusted. A draft is accepted only if ALL stages pass:
  1. static   : naming, rego.v1, no dangerous built-ins, no override of authz
  2. format   : opa fmt (normalises the draft)
  3. check    : opa check --strict on the whole policy tree
  4. tests    : opa test on the whole policy tree (the draft's own tests AND
                every existing test => regression protection)
"""
import json
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path

OPA_IMAGE = "openpolicyagent/opa:1.4.2"
ROOT = Path(__file__).resolve().parent.parent
POLICIES = ROOT / "policies"
WORK = Path(__file__).resolve().parent / ".work"
MIN_TESTS = 3

RULE_PKG = re.compile(r"^package\s+enterprise\.candidates\.([a-z][a-z0-9_]*)\s*$", re.M)
TEST_PKG = re.compile(r"^package\s+enterprise\.candidates_test\.([a-z][a-z0-9_]*)\s*$", re.M)
FORBIDDEN = {
    r"http\.send": "network access (http.send) is forbidden",
    r"opa\.runtime": "opa.runtime() is forbidden",
    r"\bnet\.": "network built-ins are forbidden",
    r"\bdefault\s+allow\b": "drafts must not define 'default allow'",
    r"^\s*allow\b": "drafts must not define 'allow'; expose a 'violation' set",
    r"\bwith\s+data\.": "drafts must not override data",
}


@dataclass
class Stage:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class GateResult:
    name: str = ""
    stages: list = field(default_factory=list)
    rule_src: str = ""
    test_src: str = ""

    @property
    def accepted(self):
        return bool(self.stages) and all(s.ok for s in self.stages)

    def report(self):
        lines = []
        for s in self.stages:
            lines.append(f"[{'PASS' if s.ok else 'FAIL'}] {s.name}" + (f": {s.detail}" if s.detail else ""))
        return "\n".join(lines)


def run_opa(args, cwd):
    """Use a local `opa` if present, else the pinned Docker image."""
    if shutil.which("opa"):
        cmd = ["opa", *args]
    else:
        cmd = ["docker", "run", "--rm", "-v", f"{cwd}:/work", "-w", "/work", OPA_IMAGE, *args]
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=180)


def static_checks(rule_src, test_src):
    problems = []
    m = RULE_PKG.search(rule_src)
    t = TEST_PKG.search(test_src)
    if not m:
        problems.append("rule package must be 'enterprise.candidates.<name>'")
    if not t:
        problems.append("test package must be 'enterprise.candidates_test.<name>'")
    if m and t and m.group(1) != t.group(1):
        problems.append("rule and test package names differ")
    for src, label in ((rule_src, "rule"), (test_src, "tests")):
        if "import rego.v1" not in src:
            problems.append(f"{label}: missing 'import rego.v1'")
        for pat, msg in FORBIDDEN.items():
            if re.search(pat, src, re.M):
                problems.append(f"{label}: {msg}")
    if not re.search(r"^violation\s+contains\b", rule_src, re.M):
        problems.append("rule must define 'violation contains <msg> if { ... }'")
    n = len(re.findall(r"^test_\w+", test_src, re.M))
    if n < MIN_TESTS:
        problems.append(f"need at least {MIN_TESTS} tests, found {n}")
    return problems, (m.group(1) if m else "")


def run_gate(rule_src, test_src):
    res = GateResult(rule_src=rule_src, test_src=test_src)
    problems, name = static_checks(rule_src, test_src)
    res.name = name
    res.stages.append(Stage("static", not problems, "; ".join(problems)))
    if problems:
        return res

    WORK.mkdir(exist_ok=True)
    tmp = WORK / f"run-{uuid.uuid4().hex[:8]}"
    try:
        shutil.copytree(POLICIES, tmp)
        cand = tmp / "candidates"
        cand.mkdir(exist_ok=True)
        (cand / f"{name}.rego").write_text(rule_src, encoding="utf-8")
        (cand / f"{name}_test.rego").write_text(test_src, encoding="utf-8")

        p = run_opa(["fmt", "-w", f"candidates/{name}.rego", f"candidates/{name}_test.rego"], tmp)
        res.stages.append(Stage("format", p.returncode == 0, (p.stderr or p.stdout).strip()[:400]))
        if p.returncode != 0:
            return res
        res.rule_src = (cand / f"{name}.rego").read_text(encoding="utf-8")
        res.test_src = (cand / f"{name}_test.rego").read_text(encoding="utf-8")

        p = run_opa(["check", "--strict", "."], tmp)
        res.stages.append(Stage("check", p.returncode == 0, (p.stderr or p.stdout).strip()[:800]))
        if p.returncode != 0:
            return res

        p = run_opa(["test", ".", "--format", "json"], tmp)
        try:
            results = json.loads(p.stdout)
            results = results if isinstance(results, list) else results.get("result", [])
        except ValueError:
            res.stages.append(Stage("tests", False, (p.stderr or p.stdout).strip()[:800]))
            return res
        own = [r for r in results if f"candidates_test.{name}" in r.get("package", "")]
        failed = [r["name"] for r in results if r.get("fail") or r.get("error")]
        total = len(results)
        ok = p.returncode == 0 and not failed and len(own) >= MIN_TESTS
        detail = f"{total - len(failed)}/{total} passed ({len(own)} from the draft)"
        if failed:
            detail += "; failing: " + ", ".join(failed)
        res.stages.append(Stage("tests", ok, detail))
        return res
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def install(res):
    """Write an accepted draft into policies/candidates/ (OPA --watch reloads it)."""
    assert res.accepted
    dest = POLICIES / "candidates"
    dest.mkdir(exist_ok=True)
    (dest / f"{res.name}.rego").write_text(res.rule_src, encoding="utf-8")
    (dest / f"{res.name}_test.rego").write_text(res.test_src, encoding="utf-8")
    return dest / f"{res.name}.rego"
