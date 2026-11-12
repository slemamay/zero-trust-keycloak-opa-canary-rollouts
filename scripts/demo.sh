#!/usr/bin/env bash
# Démo PEP -> OPA. Prérequis : docker compose up -d, Django sur :8000, jq installé.
# Usage : ./scripts/demo.sh bob 'motdepasse'
set -euo pipefail
KC=${KC:-http://localhost:8080}; API=${API:-http://localhost:8000}; REALM=${REALM:-projet44}
USER_NAME=${1:?utilisateur}; PASS=${2:?mot de passe}

# NB : le client doit autoriser le Direct Access Grant (ou récupère un token autrement)
TOKEN=$(curl -s -X POST "$KC/realms/$REALM/protocol/openid-connect/token" \
  -d grant_type=password -d client_id=django-app ${OIDC_CLIENT_SECRET:+-d client_secret=$OIDC_CLIENT_SECRET} \
  -d username="$USER_NAME" -d password="$PASS" | jq -r .access_token)

call() { echo; echo "### $1"; curl -s -o /dev/stderr -w "HTTP %{http_code}\n" -X "${2:-GET}" \
  -H "Authorization: Bearer $TOKEN" "$API$3"; }

call "Scène 1 - qui suis-je ?"                    GET  /whoami/
call "Scène 2 - approuver petit virement (AG01)"  POST /transactions/1/approve/
call "Scène 3 - approuver 50 000 (limite manager)" POST /transactions/2/approve/
call "Scène 4 - autre agence (AG02) => 403"       POST /transactions/3/approve/
echo; echo "### Derniers événements d'audit"; tail -n 4 app/logs/audit.jsonl | jq -c '{decision,user,action,resource,reasons}'