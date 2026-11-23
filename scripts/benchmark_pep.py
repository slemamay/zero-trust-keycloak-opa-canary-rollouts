#!/usr/bin/env python3
"""Benchmark PEP -> OPA (stdlib only).  Fills the 'benchmark results' slide.

  python scripts/benchmark_pep.py                 # 100 PEP->OPA decisions (allow + deny)
  python scripts/benchmark_pep.py -n 500          # more samples
  python scripts/benchmark_pep.py --e2e           # + HTTP end-to-end through Django (needs Keycloak + Django up)

Measures the real client code (authz.pep.decide), so JSON encoding, the HTTP call
and OPA evaluation are all included. Results are printed as a Markdown table and
saved to docs/benchmark.json. Use a FIXED context so the result does not depend
on the clock.
"""
import argparse
import json
import os
import statistics
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
from authz import pep  # noqa: E402  (stdlib only, no Django needed)

CTX = {"hour": 10, "weekday": "Tuesday"}
RES = {"type": "transaction", "id": "bench", "branch": "AG01", "amount": 500.0, "created_by": "alice"}
BOB = {"sub": "bob", "username": "bob", "roles": ["manager"], "branch": "AG01", "agent_scopes": []}


def pct(sorted_ms, p):
    """Nearest-rank percentile."""
    k = max(0, min(len(sorted_ms) - 1, round(p / 100 * len(sorted_ms) + 0.5) - 1))
    return sorted_ms[k]


def summarize(samples):
    s = sorted(samples)
    return {"n": len(s), "min": s[0], "mean": statistics.mean(s), "p50": pct(s, 50),
            "p95": pct(s, 95), "p99": pct(s, 99), "max": s[-1]}


def bench(fn, n, warmup):
    for _ in range(warmup):
        fn()
    out = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        out.append((time.perf_counter() - t0) * 1000)
    return summarize(out)


def pdp_case(resource, expect_allow):
    subject = pep.build_subject(BOB)

    def run():
        allow, _reasons, _ctx, err = pep.decide(subject, "approve", resource, CTX)
        if err:
            raise SystemExit(f"OPA unreachable at {pep.OPA_URL}: {err}")
        if allow is not expect_allow:
            raise SystemExit("Unexpected decision: policies/data.json changed? Restore it before benchmarking.")
    return run


def token(user, password, kc, secret):
    body = urllib.parse.urlencode({"grant_type": "password", "client_id": "django-app", "client_secret": secret,
                                   "username": user, "password": password}).encode()
    with urllib.request.urlopen(urllib.request.Request(
            f"{kc}/realms/projet44/protocol/openid-connect/token", data=body)) as r:
        return json.loads(r.read())["access_token"]


def api_case(url, tok):
    def run():
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
    return run


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=100, help="measured requests per case (default 100)")
    ap.add_argument("--warmup", type=int, default=10)
    ap.add_argument("--e2e", action="store_true", help="also time HTTP calls through Django")
    ap.add_argument("--kc", default=os.getenv("KEYCLOAK_URL", "http://localhost:8080"))
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--secret", default=os.getenv("OIDC_CLIENT_SECRET", "projet44-dev-secret"))
    a = ap.parse_args()

    results = {
        "PEP -> OPA decision (ALLOW)": bench(pdp_case(RES, True), a.n, a.warmup),
        "PEP -> OPA decision (DENY, branch mismatch)": bench(pdp_case({**RES, "branch": "AG02"}, False), a.n, a.warmup),
    }
    if a.e2e:
        tok = token("bob", "Bob123!", a.kc, a.secret)
        results["GET /whoami/ (JWT/JWKS check only)"] = bench(api_case(f"{a.api}/whoami/", tok), a.n, a.warmup)
        results["GET /transactions/ (JWT + 1 OPA call per row)"] = bench(
            api_case(f"{a.api}/transactions/", tok), a.n, a.warmup)

    print(f"\nPEP -> OPA benchmark ({a.n} requests per case after {a.warmup} warm-up, times in ms)\n")
    print("| Case | n | min | mean | p50 | p95 | p99 | max |\n|---|---|---|---|---|---|---|---|")
    for name, r in results.items():
        print(f"| {name} | {r['n']} | {r['min']:.1f} | {r['mean']:.1f} | {r['p50']:.1f} | "
              f"{r['p95']:.1f} | {r['p99']:.1f} | {r['max']:.1f} |")
    out = ROOT / "docs" / "benchmark.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"opa_url": pep.OPA_URL, "results": results}, indent=2), encoding="utf-8", newline="\n")
    print(f"\nSaved to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
