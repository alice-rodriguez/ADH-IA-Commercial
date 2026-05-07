# ADH Veille — API

API FastAPI exposant les offres collectées par le pipeline de veille de missions IT
pour ADH PM Consulting. Sert de backend à l'interface web de consultation quotidienne.

## Lancement local

```bash
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

## Endpoints disponibles

| Méthode | Endpoint  | Description                        |
|---------|-----------|------------------------------------|
| GET     | `/health` | Vérification de disponibilité      |

D'autres endpoints arrivent dans les sous-étapes suivantes (B.2 et après) :
lecture des offres, filtrage, actions utilisateur (favoris, statuts).

## Documentation Swagger

Générée automatiquement par FastAPI :

```
http://127.0.0.1:8000/docs
```
