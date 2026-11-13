# Project 44 - end-to-end validation (Windows PowerShell 5.1 or 7)
# Put this file in <repo>\scripts\ and run from the repo root:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\scripts\e2e_test.ps1
#
# Prerequisites:
#   - docker compose up -d   (postgres, keycloak, opa all running)
#   - Django running in another terminal WITH fake time:
#         cd app; $env:AUTHZ_FAKE_NOW="2026-11-12T10:00"; python manage.py runserver
param(
  [string]$KC = "http://localhost:8080",
  [string]$Api = "http://localhost:8000",
  [string]$Opa = "http://localhost:8181",
  [string]$Realm = "projet44",
  [string]$Secret = "projet44-dev-secret"
)

$Root = Split-Path -Parent $PSScriptRoot
$DataJson = Join-Path $Root "policies\data.json"
$CandDir = Join-Path $Root "policies\candidates"
$script:pass = 0; $script:fail = 0

function Check($name, [bool]$ok, $detail = "") {
  if ($ok) { $script:pass++; Write-Host "[PASS] $name" -ForegroundColor Green }
  else { $script:fail++; Write-Host "[FAIL] $name  $detail" -ForegroundColor Red }
}

function Get-Token($user, $pwd) {
  (Invoke-RestMethod -Method Post -Uri "$KC/realms/$Realm/protocol/openid-connect/token" -Body @{
    grant_type = "password"; client_id = "django-app"; client_secret = $Secret
    username = $user; password = $pwd }).access_token
}

function Call-Api($method, $path, $token) {
  $h = @{}
  if ($token) { $h["Authorization"] = "Bearer $token" }
  try {
    $r = Invoke-WebRequest -Method $method -Uri "$Api$path" -Headers $h -UseBasicParsing
    return @{ code = [int]$r.StatusCode; body = $r.Content }
  } catch {
    $code = 0
    if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
    return @{ code = $code; body = "$($_.ErrorDetails.Message)" }
  }
}

function Opa-Decision($inputObj) {
  $json = @{ input = $inputObj } | ConvertTo-Json -Depth 8
  (Invoke-RestMethod -Method Post -Uri "$Opa/v1/data/enterprise/authz/decision" -ContentType "application/json" -Body $json).result
}

function Wait-Opa {
  for ($i = 0; $i -lt 30; $i++) {
    try { Invoke-RestMethod -Uri "$Opa/health" | Out-Null; return $true } catch { Start-Sleep 1 }
  }
  return $false
}

if ($Root -match "OneDrive") {
  Write-Host "WARNING: project is inside OneDrive; the hot-swap tests may fail (file watching). Move it to C:\dev." -ForegroundColor Yellow
}

# ---------------------------------------------------------------- preflight
Write-Host "`n== Preflight ==" -ForegroundColor Cyan
$bob = Get-Token "bob" "Bob123!"
$pre = Call-Api "POST" "/transactions/1/approve/" $bob
if ($pre.code -eq 403 -and $pre.body -match "hours") {
  Write-Host "ABORT: business-hours rule is active. Restart Django with `$env:AUTHZ_FAKE_NOW=`"2026-11-12T10:00`"" -ForegroundColor Red
  exit 2
}
Check "preflight: Django + Keycloak + OPA reachable (bob approve tx1 -> 200)" ($pre.code -eq 200) "got $($pre.code) $($pre.body)"

# ---------------------------------------------------------------- authN
Write-Host "`n== Authentication (JWKS) ==" -ForegroundColor Cyan
$r = Call-Api "GET" "/whoami/" $bob
Check "whoami with valid token -> 200 manager AG01" ($r.code -eq 200 -and $r.body -match "manager" -and $r.body -match "AG01") $r.body
$r = Call-Api "GET" "/whoami/" $null
Check "no token -> 401" ($r.code -eq 401) "got $($r.code)"
$tampered = $bob.Substring(0, $bob.Length - 4) + "AAAA"
$r = Call-Api "GET" "/whoami/" $tampered
Check "tampered token -> 401" ($r.code -eq 401) "got $($r.code)"

# ---------------------------------------------------------------- authZ
Write-Host "`n== Authorization (ABAC decisions) ==" -ForegroundColor Cyan
$r = Call-Api "POST" "/transactions/1/approve/" $bob
Check "bob (manager AG01) approves 500 TND AG01 -> 200" ($r.code -eq 200) $r.body
$r = Call-Api "POST" "/transactions/2/approve/" $bob
Check "bob approves 50000 TND (= manager limit) -> 200" ($r.code -eq 200) $r.body
$r = Call-Api "POST" "/transactions/3/approve/" $bob
Check "bob approves AG02 transaction -> 403 branch mismatch" ($r.code -eq 403 -and $r.body -match "branch") $r.body
foreach ($u in @(@("alice", "Alice123!"), @("carla", "Carla123!"), @("agent-ia", "Agent123!"))) {
  $t = Get-Token $u[0] $u[1]
  $r = Call-Api "POST" "/transactions/1/approve/" $t
  Check "$($u[0]) cannot approve -> 403" ($r.code -eq 403) "got $($r.code) $($r.body)"
}
$r = Call-Api "GET" "/transactions/" (Get-Token "carla" "Carla123!")
Check "carla (auditeur) can list transactions -> 200" ($r.code -eq 200) "got $($r.code)"
$r = Call-Api "GET" "/transactions/" (Get-Token "bob" "Bob123!")
Check "bob can list transactions -> 200" ($r.code -eq 200) "got $($r.code)"

# ---------------------------------------------------------------- hot swap
Write-Host "`n== Hot-swap: edit data.json, no Django restart ==" -ForegroundColor Cyan
$original = [IO.File]::ReadAllText($DataJson)
try {
  if (([regex]::Matches($original, "50000")).Count -ne 1) {
    Check "hot-swap: exactly one '50000' in data.json" $false "edit manually, see scripts/hot_swap_demo.md"
  } else {
    [IO.File]::WriteAllText($DataJson, $original.Replace("50000", "10000"), (New-Object Text.UTF8Encoding($false)))
    Start-Sleep 4
    $r = Call-Api "POST" "/transactions/2/approve/" (Get-Token "bob" "Bob123!")
    Check "after limit 50000 -> 10000: same request now 403" ($r.code -eq 403) "got $($r.code) $($r.body)"
  }
} finally {
  [IO.File]::WriteAllText($DataJson, $original, (New-Object Text.UTF8Encoding($false)))
  Start-Sleep 4
}
$r = Call-Api "POST" "/transactions/2/approve/" (Get-Token "bob" "Bob123!")
Check "after restoring data.json: 200 again" ($r.code -eq 200) "got $($r.code) $($r.body)"

# ---------------------------------------------------------------- fail closed
Write-Host "`n== Fail-closed: OPA stopped ==" -ForegroundColor Cyan
Push-Location $Root
try {
  docker compose stop opa | Out-Null
  Start-Sleep 2
  $r = Call-Api "POST" "/transactions/1/approve/" (Get-Token "bob" "Bob123!")
  Check "OPA down -> 503 (never allow)" ($r.code -eq 503) "got $($r.code) $($r.body)"
} finally {
  docker compose start opa | Out-Null
  Check "OPA restarted and healthy" (Wait-Opa)
  Pop-Location
}

# ---------------------------------------------------------------- opa test
Write-Host "`n== opa test (Docker, pinned 1.4.2) ==" -ForegroundColor Cyan
docker run --rm -v "$($Root)\policies:/policies" openpolicyagent/opa:1.4.2 test /policies | Out-Null
Check "opa test exits 0" ($LASTEXITCODE -eq 0)
docker run --rm -v "$($Root)\policies:/policies" openpolicyagent/opa:1.4.2 check --strict /policies | Out-Null
Check "opa check --strict exits 0" ($LASTEXITCODE -eq 0)
docker run --rm -v "$($Root)\policies:/policies" openpolicyagent/opa:1.4.2 fmt --list --fail /policies | Out-Null
Check "opa fmt --fail exits 0 (already formatted)" ($LASTEXITCODE -eq 0)

# ---------------------------------------------------------------- AI assistant
Write-Host "`n== AI policy assistant (mock provider) ==" -ForegroundColor Cyan
$fridayInput = @{
  subject  = @{ sub = "bob"; type = "human"; roles = @("manager"); branch = "AG01"; agent_scopes = @() }
  resource = @{ type = "transaction"; id = "9"; branch = "AG01"; amount = 40000; created_by = "alice" }
  action   = "approve"
  context  = @{ hour = 15; weekday = "Friday" }
}
$before = Opa-Decision $fridayInput
Check "before AI rule: Friday 15h approve 40000 is allowed" ($before.allow -eq $true) ($before | ConvertTo-Json -Compress)
try {
  $out = python (Join-Path $Root "ai-assistant\assistant.py") "Approvals above 30000 TND are forbidden on Friday after 14:00" --provider mock 2>&1 | Out-String
  Check "assistant exits 0 (a draft was accepted)" ($LASTEXITCODE -eq 0) $out
  Check "attempt 1 rejected by the gate, attempt 2 accepted" ($out -match "REJECTED" -and $out -match "ACCEPTED")
  Check "accepted rule file written" (Test-Path (Join-Path $CandDir "friday_large_approval.rego"))
  Start-Sleep 4
  $after = Opa-Decision $fridayInput
  Check "after AI rule: same input is denied with the new reason" ($after.allow -eq $false -and ($after.reasons -join " ") -match "Friday") ($after | ConvertTo-Json -Compress)
} finally {
  Remove-Item (Join-Path $CandDir "*.rego") -ErrorAction SilentlyContinue
  Start-Sleep 4
}
$restored = Opa-Decision $fridayInput
Check "after removing the rule: allowed again" ($restored.allow -eq $true)

# ---------------------------------------------------------------- python unit tests
Write-Host "`n== Python unit tests ==" -ForegroundColor Cyan
Push-Location (Join-Path $Root "app")
python manage.py test authz 2>&1 | Out-Null
Check "Django: python manage.py test authz" ($LASTEXITCODE -eq 0)
Pop-Location
Push-Location $Root
python -m unittest discover -s ai-assistant 2>&1 | Out-Null
Check "AI gate self-tests (accept / reject / unsafe)" ($LASTEXITCODE -eq 0)
Pop-Location

Write-Host "`n== Result: $($script:pass) passed, $($script:fail) failed ==" -ForegroundColor $(if ($script:fail) { "Red" } else { "Green" })
exit $(if ($script:fail) { 1 } else { 0 })
