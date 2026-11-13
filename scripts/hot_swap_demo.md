# Démo hot-swap : changer une règle sans redémarrer Django

OPA tourne avec `--watch` sur `/policies` (volume `./policies`) : il recharge
dès qu'un fichier change. Django n'est jamais touché.

## Préparation
1. `docker compose up -d` puis lancer Django (`python manage.py runserver`).
2. Dans un 2e terminal : `tail -f app/logs/audit.jsonl | jq -c .`
3. Prendre un token de **bob** (manager, agence AG01).

## Scène A - Montant
1. Avant : `POST /transactions/2/approve/` (montant 50 000, limite manager 50 000) => **200**.
   Remettre la transaction en PENDING (admin Django) pour rejouer.
2. Éditer `policies/data.json` : `"manager": 50000` -> `"manager": 10000`. Sauvegarder.
3. Rejouer la même requête => **403**, `reasons: ["amount above allowed limit"]`.
4. Capture : audit.jsonl avant/après. **Aucun redémarrage de Django.**

## Scène B - Heures ouvrables
- Éditer `business_hours.end` : `18` -> `23`, rejouer une approbation à 20 h => autorisée.
- Pour simuler la nuit / le week-end sans attendre :
  `AUTHZ_FAKE_NOW=2026-11-14T22:00 python manage.py runserver` (démo seulement).

## Vérification rapide côté OPA
    curl -s localhost:8181/v1/data/config/amount_limits | jq

## Retour arrière
`git checkout policies/data.json`