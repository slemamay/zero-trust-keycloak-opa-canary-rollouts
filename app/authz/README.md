# Livrable Membre 4 - PEP middleware, audit, hot-swap
| Fichier | Statut |
|---|---|
| app/authz/{__init__,pep,middleware,audit,tests}.py | nouveau |
| app/banking/views.py | remplace (retire les if/else, filtre la liste via OPA) |
| app/config/settings.py | remplace (ajoute app `authz`, middleware, OPA_URL) |
| docker-compose.yml | corrige le volume OPA (`./policies`) + image épinglée |
| scripts/demo.sh, scripts/hot_swap_demo.md | nouveau |