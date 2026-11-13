# PowerShell demo (Windows): token for a user, then a few API calls.
# Prereqs: docker compose up -d ; Django running on :8000
# Usage:  .\scripts\demo.ps1 -User bob -Password 'Bob123!'
param(
  [Parameter(Mandatory)][string]$User,
  [Parameter(Mandatory)][string]$Password,
  [string]$KC = "http://localhost:8080",
  [string]$Api = "http://localhost:8000",
  [string]$Realm = "projet44",
  [string]$Secret = "projet44-dev-secret"
)
$tok = Invoke-RestMethod -Method Post -Uri "$KC/realms/$Realm/protocol/openid-connect/token" -Body @{
  grant_type = "password"; client_id = "django-app"; client_secret = $Secret
  username = $User; password = $Password }
$h = @{ Authorization = "Bearer $($tok.access_token)" }

function Call($label, $method, $path) {
  Write-Host "`n### $label" -ForegroundColor Cyan
  try {
    $r = Invoke-WebRequest -Method $method -Uri "$Api$path" -Headers $h -UseBasicParsing
    Write-Host "HTTP $($r.StatusCode)"; Write-Host $r.Content
  } catch {
    $code = [int]$_.Exception.Response.StatusCode
    Write-Host "HTTP $code"; if ($_.ErrorDetails.Message) { Write-Host $_.ErrorDetails.Message }
  }
}
Call "Scene 1 - whoami"                          GET  "/whoami/"
Call "Scene 2 - approve small transfer (AG01)"   POST "/transactions/1/approve/"
Call "Scene 3 - approve 50 000 (manager limit)"  POST "/transactions/2/approve/"
Call "Scene 4 - other branch (AG02) => 403"      POST "/transactions/3/approve/"
Write-Host "`n### Last audit events" -ForegroundColor Cyan
Get-Content app\logs\audit.jsonl -Tail 4
