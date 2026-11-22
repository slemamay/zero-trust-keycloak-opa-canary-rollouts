#!/usr/bin/env python3
"""Console de démonstration - Projet 44 (Keycloak + OPA).  Python standard uniquement.

  python scripts\\demo_ui.py          ->  http://localhost:9000

Prérequis : docker compose up -d  et  Django lancé (avec AUTHZ_FAKE_NOW).
Le serveur n'écoute que sur 127.0.0.1 et ne modifie pas le code de Django.
"""
import base64, json, os, re, subprocess, sys, threading, time, urllib.error, urllib.parse, urllib.request, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(os.environ.get("DEMO_ROOT") or Path(__file__).resolve().parent.parent)
KC = os.environ.get("KC_URL", "http://localhost:8080")
API = os.environ.get("API_URL", "http://localhost:8000")
OPA = os.environ.get("OPA_URL", "http://localhost:8181")
PORT = int(os.environ.get("DEMO_PORT", "9000"))
NO_DOCKER = bool(os.environ.get("DEMO_NO_DOCKER"))
SECRET = "projet44-dev-secret"
USERS = {"alice": "Alice123!", "bob": "Bob123!", "carla": "Carla123!", "agent-ia": "Agent123!"}
BUSINESS = {"caissier", "manager", "auditeur"}
DATA_JSON = ROOT / "policies" / "data.json"
CAND = ROOT / "policies" / "candidates"
AUDIT = ROOT / "app" / "logs" / "audit.jsonl"

_tok, _lock = {}, threading.Lock()


def http(method, url, body=None, headers=None, form=False, timeout=15):
    data = None
    h = dict(headers or {})
    if body is not None:
        data = urllib.parse.urlencode(body).encode() if form else json.dumps(body).encode()
        h.setdefault("Content-Type", "application/x-www-form-urlencoded" if form else "application/json")
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # connexion refusée, timeout...
        return 0, str(e)


def decode(part):
    part += "=" * (-len(part) % 4)
    return json.loads(base64.urlsafe_b64decode(part.encode()))


def get_token(user):
    with _lock:
        t = _tok.get(user)
        if t and t[1] > time.time() + 20:
            return t[0]
    st, txt = http("POST", f"{KC}/realms/projet44/protocol/openid-connect/token",
                   {"grant_type": "password", "client_id": "django-app", "client_secret": SECRET,
                    "username": user, "password": USERS[user]}, form=True)
    if st != 200:
        raise RuntimeError(f"Keycloak injoignable ou refus ({st})")
    jwt = json.loads(txt)["access_token"]
    exp = decode(jwt.split(".")[1]).get("exp", time.time() + 200)
    with _lock:
        _tok[user] = (jwt, exp)
    return jwt


def call(user, action, tx, mode):
    if user not in USERS:
        return {"error": "utilisateur inconnu"}
    jwt, claims = None, None
    if mode != "none":
        try:
            jwt = get_token(user)
        except RuntimeError as e:
            return {"status": 0, "error": str(e), "stage": "keycloak"}
        p = decode(jwt.split(".")[1])
        claims = {"username": p.get("preferred_username"), "iss": p.get("iss"), "azp": p.get("azp"),
                  "roles": [r for r in p.get("realm_access", {}).get("roles", []) if r in BUSINESS],
                  "agence": p.get("agence"), "agent_scopes": p.get("agent_scopes", [])}
        if mode == "tampered":
            jwt = jwt[:-4] + "AAAA"
    method, path = {"whoami": ("GET", "/whoami/"), "list": ("GET", "/transactions/"),
                    "approve": ("POST", f"/transactions/{int(tx)}/approve/")}[action]
    headers = {"Authorization": f"Bearer {jwt}"} if jwt else {}
    st, txt = http(method, API + path, headers=headers)
    try:
        body = json.loads(txt)
    except ValueError:
        body = txt[:300]
    return {"status": st, "body": body, "claims": claims, "request": f"{method} {path}"}


def ping(url):
    st, _ = http("GET", url, timeout=3)
    return st != 0


def read_limit():
    m = re.search(r'"amount_limits"\s*:\s*\{[^}]*"manager"\s*:\s*(\d+)', DATA_JSON.read_text(encoding="utf-8"))
    return int(m.group(1)) if m else None


def wait_opa(sec=30):
    for _ in range(sec * 2):
        if http("GET", OPA + "/health", timeout=2)[0] == 200:
            return True
        time.sleep(0.5)
    return False


def reload_opa():
    t0 = time.time()
    if NO_DOCKER:
        time.sleep(1.5)
        return True, round(time.time() - t0, 1)
    subprocess.run(["docker", "compose", "restart", "opa"], cwd=ROOT, capture_output=True, timeout=90)
    return wait_opa(), round(time.time() - t0, 1)


def set_limit(value):
    value = int(value)
    if not 1 <= value <= 10_000_000:
        raise ValueError("valeur hors limites")
    txt = DATA_JSON.read_text(encoding="utf-8")
    new, n = re.subn(r'("amount_limits"\s*:\s*\{[^}]*"manager"\s*:\s*)\d+', lambda m: m.group(1) + str(value), txt, count=1)
    if n != 1:
        raise ValueError("limite manager introuvable dans data.json")
    DATA_JSON.write_text(new, encoding="utf-8")
    ok, secs = reload_opa()
    return {"limit": read_limit(), "opa_ok": ok, "seconds": secs}


def opa_ctl(action):
    if not NO_DOCKER:
        subprocess.run(["docker", "compose", action, "opa"], cwd=ROOT, capture_output=True, timeout=90)
    return {"opa_up": http("GET", OPA + "/health", timeout=2)[0] == 200 if action == "start" and wait_opa() else False}


def candidates():
    return sorted(p.stem for p in CAND.glob("*.rego") if not p.stem.endswith("_test")) if CAND.exists() else []


def run_assistant(req, provider, model):
    if provider == "openai":
        model = os.environ.get("LLM_MODEL") or "gemini-3.8-flash"
    env = os.environ.copy()
    env.setdefault("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")
    cmd = [sys.executable, str(ROOT / "ai-assistant" / "assistant.py"), req, "--provider", provider, "--model", model]
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=300, env=env)
    out = (p.stdout + p.stderr).strip()
    res = {"output": out, "accepted": p.returncode == 0}
    if p.returncode == 0:
        ok, secs = reload_opa()
        res.update(opa_ok=ok, seconds=secs)
    res["candidates"] = candidates()
    return res


def remove_rules():
    for f in CAND.glob("*.rego"):
        f.unlink()
    ok, secs = reload_opa()
    return {"candidates": candidates(), "opa_ok": ok, "seconds": secs}


def friday():
    inp = {"input": {"subject": {"sub": "bob", "type": "human", "roles": ["manager"], "branch": "AG01", "agent_scopes": []},
                     "resource": {"type": "transaction", "id": "9", "branch": "AG01", "amount": 40000, "created_by": "alice"},
                     "action": "approve", "context": {"hour": 15, "weekday": "Friday"}}}
    st, txt = http("POST", OPA + "/v1/data/enterprise/authz/decision", inp)
    return {"status": st, "result": json.loads(txt).get("result") if st == 200 else txt}


def audit(n=8):
    if not AUDIT.exists():
        return []
    rows = []
    for ln in AUDIT.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]:
        try:
            e = json.loads(ln)
            rows.append({"ts": e.get("ts", "")[11:19], "user": e.get("user"), "action": e.get("action"),
                         "tx": (e.get("resource") or {}).get("id"), "decision": e.get("decision"),
                         "reasons": e.get("reasons") or []})
        except ValueError:
            pass
    return rows[::-1]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, obj, code=200, ctype="application/json"):
        raw = obj.encode() if isinstance(obj, str) else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        try:
            if self.path == "/":
                return self.send(PAGE, ctype="text/html")
            if self.path == "/api/status":
                return self.send({"keycloak": ping(KC + "/realms/projet44/.well-known/openid-configuration"),
                                  "opa": http("GET", OPA + "/health", timeout=3)[0] == 200,
                                  "django": ping(API + "/whoami/")})
            if self.path == "/api/audit":
                return self.send(audit())
            if self.path == "/api/state":
                return self.send({"limit": read_limit(), "candidates": candidates()})
            self.send({"error": "not found"}, 404)
        except Exception as e:
            self.send({"error": str(e)}, 500)

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            b = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/api/call":
                return self.send(call(b.get("user"), b.get("action"), b.get("id", 1), b.get("token", "valid")))
            if self.path == "/api/limit":
                return self.send(set_limit(b["value"]))
            if self.path == "/api/opa":
                return self.send(opa_ctl("start" if b.get("on") else "stop"))
            if self.path == "/api/assistant":
                return self.send(run_assistant(b["requirement"], b.get("provider", "mock"), b.get("model", "qwen2.5-coder:7b")))
            if self.path == "/api/remove-rule":
                return self.send(remove_rules())
            if self.path == "/api/friday":
                return self.send(friday())
            self.send({"error": "not found"}, 404)
        except Exception as e:
            self.send({"error": str(e)}, 500)


PAGE = r"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Projet 44 - Console de démonstration</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--red:#8D0000;--pink:#FFE9E9;--pink2:#FFCDCD;--ink:#2B1B1B;--ok:#2E7D32;--bad:#C62828;--warn:#E65100;--mute:#8a6a6a}
*{box-sizing:border-box}body{margin:0;font-family:Poppins,"Segoe UI",system-ui,sans-serif;color:var(--ink);background:#fff;font-size:17px}
header{display:flex;align-items:center;justify-content:space-between;padding:14px 28px;background:var(--red);color:#fff}
header h1{margin:0;font-size:24px}.pills{display:flex;gap:10px}.pill{padding:6px 14px;border-radius:20px;font-size:15px;background:#ffffff22;font-weight:600}
.pill.up{background:#2E7D32}.pill.down{background:#C62828}
main{padding:18px 28px;display:grid;gap:18px}
.row{display:grid;gap:18px}.r1{grid-template-columns:1fr 1.15fr 1.5fr}.r2{grid-template-columns:1.3fr 1fr 1.2fr}
.card{background:var(--pink);border:2px solid var(--pink2);border-radius:16px;padding:16px 18px}
.card h2{margin:0 0 10px;font-size:18px;color:var(--red)}.sub{color:var(--mute);font-size:14px;margin:-6px 0 10px}
button{font:inherit;cursor:pointer;border:2px solid var(--red);background:#fff;color:var(--red);border-radius:10px;padding:9px 14px;font-weight:600}
button:hover{background:var(--red);color:#fff}button.primary{background:var(--red);color:#fff}button:disabled{opacity:.5;cursor:wait}
.user{display:block;width:100%;text-align:left;margin-bottom:8px}.user small{display:block;font-weight:400;opacity:.85}
.user.sel{background:var(--red);color:#fff}
.acts button{display:block;width:100%;margin-bottom:8px;text-align:left}
.modes{display:flex;gap:6px;margin:6px 0 10px;flex-wrap:wrap}.modes button{padding:5px 10px;font-size:14px}.modes button.sel{background:var(--red);color:#fff}
.steps{display:flex;gap:6px;align-items:stretch;margin-bottom:12px}
.step{flex:1;border-radius:10px;padding:8px 6px;text-align:center;font-size:13px;font-weight:600;background:#fff;border:2px solid #ddd;color:#999}
.step.ok{border-color:var(--ok);color:var(--ok)}.step.bad{border-color:var(--bad);background:#FDECEA;color:var(--bad)}.step.na{border-style:dashed}
.verdict{border-radius:12px;padding:14px;text-align:center;font-size:26px;font-weight:700;color:#fff;background:#999;margin-bottom:10px}
.verdict.ok{background:var(--ok)}.verdict.bad{background:var(--bad)}.verdict.warn{background:var(--warn)}
.why{font-size:17px;margin:6px 0}.mono,pre{font-family:Consolas,monospace;font-size:13px;background:#1e1414;color:#f3dede;border-radius:10px;padding:10px;overflow:auto;white-space:pre-wrap;word-break:break-word}
table{width:100%;border-collapse:collapse;font-size:14px}th{text-align:left;color:var(--red);border-bottom:2px solid var(--pink2);padding:4px}td{padding:4px;border-bottom:1px solid var(--pink2)}
.tag{padding:2px 8px;border-radius:8px;color:#fff;font-weight:700;font-size:12px}.tag.ALLOW{background:var(--ok)}.tag.DENY{background:var(--bad)}
input[type=number],textarea,select{font:inherit;width:100%;border:2px solid var(--pink2);border-radius:10px;padding:8px;background:#fff}
textarea{height:70px;resize:vertical}.hint{font-size:14px;color:var(--mute)}.big{font-size:30px;font-weight:700;color:var(--red)}
details summary{cursor:pointer;color:var(--red);font-weight:600;margin:6px 0}
</style></head><body>
<header><h1>Projet 44 &mdash; Zero Trust : Keycloak + OPA</h1>
<div class="pills"><span class="pill" id="p-keycloak">Keycloak</span><span class="pill" id="p-opa">OPA</span><span class="pill" id="p-django">Django</span></div></header>
<main>
<div class="row r1">
 <div class="card"><h2>1. Qui êtes-vous ?</h2><div class="sub">Connexion via Keycloak (jeton JWT)</div>
  <div id="users"></div>
  <div class="sub" style="margin-top:8px">Jeton envoyé :</div>
  <div class="modes" id="modes"></div></div>
 <div class="card"><h2>2. Que voulez-vous faire ?</h2><div class="sub">Transactions de démonstration</div>
  <table style="margin-bottom:10px"><tr><th>#</th><th>Agence</th><th>Montant</th></tr>
  <tr><td>1</td><td>AG01 Tunis</td><td>500 TND</td></tr><tr><td>2</td><td>AG01 Tunis</td><td>50 000 TND</td></tr><tr><td>3</td><td>AG02 Sfax</td><td>800 TND</td></tr></table>
  <div class="acts">
   <button onclick="act('approve',1)">Approuver #1 (500 TND, AG01)</button>
   <button onclick="act('approve',2)">Approuver #2 (50 000 TND, AG01)</button>
   <button onclick="act('approve',3)">Approuver #3 (800 TND, AG02)</button>
   <button onclick="act('list')">Voir les transactions visibles</button>
   <button onclick="act('whoami')">Qui suis-je ? (identité du jeton)</button></div></div>
 <div class="card"><h2>3. Ce qui se passe</h2>
  <div class="steps"><div class="step na" id="s1">① Jeton<br>Keycloak</div><div class="step na" id="s2">② Vérif. JWT<br>Django (PEP)</div><div class="step na" id="s3">③ Décision<br>OPA (PDP)</div><div class="step na" id="s4">④ Journal<br>d'audit</div></div>
  <div class="verdict" id="verdict">En attente</div>
  <div class="why" id="why">Choisissez un utilisateur puis une action.</div>
  <div id="extra"></div>
  <details><summary>Détails techniques</summary><div class="mono" id="tech">-</div></details></div>
</div>
<div class="row r2">
 <div class="card"><h2>Journal d'audit (une ligne par décision)</h2>
  <table><thead><tr><th>Heure</th><th>Utilisateur</th><th>Action</th><th>Tx</th><th>Décision</th><th>Raison</th></tr></thead><tbody id="audit"></tbody></table></div>
 <div class="card"><h2>Changer une règle sans redéployer</h2>
  <div class="sub">Limite d'approbation du manager (policies/data.json)</div>
  <div class="big" id="limit">-</div><div class="hint">TND</div>
  <input type="number" id="newlimit" value="10000" min="1" style="margin:8px 0">
  <button class="primary" onclick="setLimit(+document.getElementById('newlimit').value)">Appliquer la nouvelle limite</button>
  <button onclick="setLimit(50000)" style="margin-top:6px">Rétablir 50 000</button>
  <div class="hint" id="limitmsg" style="margin-top:8px">Django n'est jamais redémarré : seule la donnée change.</div>
  <hr style="border:0;border-top:2px solid var(--pink2);margin:14px 0">
  <h2>Panne du moteur de décision</h2>
  <button id="opabtn" onclick="toggleOpa()">Arrêter OPA (simuler une panne)</button>
  <div class="hint" style="margin-top:6px">Sans OPA, tout est refusé (fail-closed).</div></div>
 <div class="card"><h2>Assistant IA de politiques</h2>
  <div class="sub">Exigence en texte libre &rarr; règle Rego &rarr; porte de tests OPA</div>
  <textarea id="req">Approvals above 30000 TND are forbidden on Friday after 14:00</textarea>
  <select id="prov" style="margin:6px 0"><option value="mock">Démo hors ligne (brouillons préparés)</option><option value="ollama">Ollama local (LLM réel)</option><option value="openai">Gemini / API (clé dans LLM_API_KEY)</option></select>
  <button class="primary" id="aibtn" onclick="runAI()">Générer et tester</button>
  <pre id="aiout" style="max-height:170px;margin-top:8px;display:none"></pre>
  <div id="aistate" class="hint" style="margin-top:6px"></div>
  <button onclick="fri()" style="margin-top:6px">Tester : bob approuve 40 000 TND, vendredi 15h</button>
  <button onclick="rmRule()" style="margin-top:6px">Retirer la règle IA</button>
  <div id="fri" class="why"></div></div>
</div></main>
<script>
const USERS=[["alice","alice","caissier · agence AG01"],["bob","bob","manager · agence AG01"],["carla","carla","auditeur · toutes agences"],["agent-ia","agent-ia","agent IA · scopes : lire, brouillon"]];
const MODES=[["valid","Valide"],["tampered","Altéré"],["none","Absent"]];
const R={"branch mismatch":"agence différente de celle de la transaction","amount above allowed limit":"montant supérieur à la limite autorisée","outside business hours":"hors heures ouvrables (lun-ven, 8h-18h)","cannot approve own transaction":"on ne peut pas approuver sa propre transaction","action not permitted for this role/agent scope":"action non autorisée pour ce rôle ou ce scope","pdp_unavailable":"OPA injoignable : refus par défaut","denied_by_policy":"refusé par la politique","large approval blocked on Friday afternoon":"règle IA : grosses approbations bloquées le vendredi après 14h"};
const fr=r=>R[r]||r;let user="bob",mode="valid",opaOn=true;
const $=id=>document.getElementById(id);
async function j(u,b){const r=await fetch(u,b===undefined?{}:{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)});return r.json()}
function draw(){$("users").innerHTML=USERS.map(([k,n,d])=>`<button class="user ${k===user?"sel":""}" onclick="user='${k}';draw()">${n}<small>${d}</small></button>`).join("");
$("modes").innerHTML=MODES.map(([k,l])=>`<button class="${k===mode?"sel":""}" onclick="mode='${k}';draw()">${l}</button>`).join("")}
function steps(a,v){const s=["na","na","na","na"];
 if(v.mode==="none"){s[0]="bad"}else if(v.mode==="tampered"){s[0]="ok";s[1]="bad"}
 else if(v.status===0){s[0]=v.stage==="keycloak"?"bad":"ok";s[1]=v.stage==="keycloak"?"na":"bad"}
 else if(v.status===401){s[0]="ok";s[1]="bad"}
 else if(a==="whoami"){s[0]="ok";s[1]="ok"}
 else if(v.status===200){s.fill("ok")}
 else if(v.status===403||v.status===503){s[0]="ok";s[1]="ok";s[2]="bad";s[3]="ok"}
 s.forEach((c,i)=>$("s"+(i+1)).className="step "+c)}
async function act(a,id){document.querySelectorAll("button").forEach(b=>b.disabled=true);
 let v;try{v=await j("/api/call",{user,action:a,id,token:mode})}catch(e){v={status:0,error:String(e)}}
 document.querySelectorAll("button").forEach(b=>b.disabled=false);v.mode=mode;render(a,id,v);loadAudit()}
function render(a,id,v){steps(a,v);const V=$("verdict");let cls="",t="",w="";const rs=(v.body&&v.body.reasons)||[];
 const who=v.claims?`${v.claims.username} (${(v.claims.roles.join(", ")||"agent IA")}${v.claims.agence?", "+v.claims.agence:""})`:user;
 if(v.status===0){cls="warn";t="Service injoignable";w=v.error||"Django ne répond pas."}
 else if(v.status===401){cls="warn";t="🔒 NON AUTHENTIFIÉ (401)";w=v.mode==="none"?"Aucun jeton : Django refuse la requête.":"La signature du jeton est invalide : Django refuse avant même d'appeler OPA."}
 else if(v.status===503){cls="bad";t="⛔ OPA INJOIGNABLE";w="Le moteur de décision est arrêté : par sécurité, tout est refusé (fail-closed)."}
 else if(v.status===403){cls="bad";t="✖ REFUSÉ (403)";w="OPA a refusé : "+(rs.map(fr).join(" ; ")||"refus par la politique")+"."}
 else if(v.status===200){cls="ok";
  if(a==="approve"){t="✔ AUTORISÉ (200)";w=`${who} a approuvé la transaction #${id} : rôle, agence, montant, heures et séparation des tâches sont conformes.`}
  else if(a==="whoami"){t="✔ IDENTITÉ VÉRIFIÉE";w="Django a vérifié la signature avec les clés publiques de Keycloak (JWKS) : aucun appel à OPA, aucune session."}
  else{t="✔ LISTE FILTRÉE";w=`${(v.body||[]).length} transaction(s) visible(s) pour ${who} : OPA décide ligne par ligne.`}}
 else{cls="warn";t="Statut "+v.status;w=JSON.stringify(v.body)}
 V.className="verdict "+cls;V.textContent=t;$("why").textContent=w;
 let x="";if(v.claims){x+=`<div class="sub" style="margin-top:8px">Ce que contient le jeton (lu par Django et OPA) :</div><table><tr><td>utilisateur</td><td>${v.claims.username}</td></tr><tr><td>rôle</td><td>${v.claims.roles.join(", ")||"aucun (agent IA)"}</td></tr><tr><td>agence</td><td>${v.claims.agence||"-"}</td></tr><tr><td>scopes agent</td><td>${(v.claims.agent_scopes||[]).join(", ")||"-"}</td></tr></table>`}
 if(a==="list"&&Array.isArray(v.body)&&v.body.length){x+=`<table style="margin-top:8px"><tr><th>#</th><th>Agence</th><th>Montant</th><th>Statut</th></tr>${v.body.map(r=>`<tr><td>${r.id}</td><td>${r.branch__code}</td><td>${r.amount}</td><td>${r.status}</td></tr>`).join("")}</table>`}
 $("extra").innerHTML=x;$("tech").textContent=`${v.request||""}\nHTTP ${v.status}\n`+JSON.stringify(v.body,null,1)}
async function loadAudit(){try{const a=await j("/api/audit");$("audit").innerHTML=a.map(e=>`<tr><td>${e.ts}</td><td>${e.user}</td><td>${e.action}</td><td>${e.tx??""}</td><td><span class="tag ${e.decision}">${e.decision}</span></td><td>${(e.reasons||[]).map(fr).join(" ; ")}</td></tr>`).join("")}catch(e){}}
async function loadState(){const s=await j("/api/state");$("limit").textContent=s.limit==null?"?":s.limit.toLocaleString("fr-FR");
 $("aistate").textContent=s.candidates.length?"Règle IA active : "+s.candidates.join(", "):"Aucune règle IA active."}
async function loadStatus(){try{const s=await j("/api/status");for(const k of["keycloak","opa","django"])$("p-"+k).className="pill "+(s[k]?"up":"down");opaOn=s.opa;$("opabtn").textContent=opaOn?"Arrêter OPA (simuler une panne)":"Redémarrer OPA"}catch(e){}}
async function setLimit(v){$("limitmsg").textContent="Rechargement d'OPA...";const r=await j("/api/limit",{value:v});
 $("limitmsg").textContent=r.error?("Erreur : "+r.error):`Limite = ${r.limit} TND. OPA rechargé en ${r.seconds} s. Django n'a pas été redémarré.`;loadState();loadStatus()}
async function toggleOpa(){$("opabtn").disabled=true;$("opabtn").textContent="...";await j("/api/opa",{on:!opaOn});await loadStatus();$("opabtn").disabled=false}
async function runAI(){const b=$("aibtn");b.disabled=true;b.textContent="Génération et tests en cours...";const o=$("aiout");o.style.display="block";o.textContent="";
 const r=await j("/api/assistant",{requirement:$("req").value,provider:$("prov").value});b.disabled=false;b.textContent="Générer et tester";
 o.textContent=r.error?("Erreur : "+r.error):r.output;o.scrollTop=o.scrollHeight;loadState();loadStatus()}
async function rmRule(){$("aistate").textContent="Retrait et rechargement d'OPA...";await j("/api/remove-rule",{});$("fri").textContent="";loadState();loadStatus()}
async function fri(){const r=await j("/api/friday",{});const d=r.result;if(!d||d.allow===undefined){$("fri").textContent="OPA ne répond pas.";return}
 $("fri").innerHTML=d.allow?"<b style='color:var(--ok)'>AUTORISÉ</b> : aucune règle IA ne s'applique.":"<b style='color:var(--bad)'>REFUSÉ</b> : "+(d.reasons||[]).map(fr).join(" ; ")}
draw();loadState();loadStatus();loadAudit();setInterval(loadStatus,4000);setInterval(loadAudit,5000);
</script></body></html>"""

if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"Console de démonstration : http://localhost:{PORT}  (Ctrl+C pour arrêter)")
    if not os.environ.get("DEMO_NO_BROWSER"):
        threading.Timer(0.8, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
