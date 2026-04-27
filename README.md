# Agent IA ADH — Digest Quotidien d'Opportunités

Agent automatique qui collecte chaque matin les offres d'emploi et appels d'offres
pertinents pour ADH Project Management Consulting, les filtre intelligemment,
les associe aux meilleurs CVs de votre base, et vous envoie un digest par email.

---

## Flux de données

```
Sources web (BOAMP, APEC, Indeed, WTJ, Freelance.com)
         │  [Collecte en parallèle — toutes les sources simultanément]
         ▼
   Déduplication SQLite
   [Élimine les offres déjà vues dans les 7 derniers jours]
         │
         ▼
   Passe 1 — Filtre mots-clés (GRATUIT)
   [Élimine ~70-80% des offres hors cible sans appeler l'IA]
         │
         ▼
   Passe 2 — Filtre IA (Claude Haiku)
   [Score 0-100, résumé en français, ~€0.001/offre]
         │
         ▼
   Matching CV (TF-IDF — GRATUIT)
   [Top 3 profils de votre base pour chaque offre retenue]
         │
         ▼
   Email digest HTML aux couleurs ADH
   [Envoi à 07h00 via Microsoft 365, du lundi au vendredi]
```

---

## Coût mensuel estimé

| Volume d'offres brutes / jour | Offres après filtre 1 | Coût IA / mois |
|-------------------------------|----------------------|----------------|
| 50 offres                     | ~10-15               | ~€0.10         |
| 150 offres                    | ~25-40               | ~€0.30         |
| 300 offres                    | ~50-80               | ~€0.60         |

**Total : bien inférieur à €5/mois** (GitHub Actions gratuit, SQLite gratuit, M365 déjà inclus).

---

## Installation pas à pas

### Étape 1 — Récupérer le projet

Si vous avez GitHub Desktop, clonez ce dépôt.
Sinon, téléchargez le projet en ZIP depuis GitHub.

### Étape 2 — Installer Python

Téléchargez Python 3.11 sur python.org et installez-le.
Cochez la case "Add Python to PATH" pendant l'installation.

### Étape 3 — Installer les dépendances

Ouvrez un terminal dans le dossier du projet et tapez :
```bash
pip install -r requirements.txt
```

### Étape 4 — Configurer vos identifiants

1. Copiez le fichier `.env.example` et renommez la copie `.env`
2. Ouvrez `.env` et remplissez vos informations :
   - `ANTHROPIC_API_KEY` : votre clé API Anthropic (créez-en une sur console.anthropic.com)
   - `EMAIL_EXPEDITEUR` : votre adresse email Microsoft 365
   - `EMAIL_MOT_DE_PASSE` : un mot de passe d'application M365 (pas votre mot de passe habituel)

**Comment créer un mot de passe d'application M365 :**
1. Connectez-vous sur myaccount.microsoft.com
2. Cliquez sur "Informations de sécurité"
3. "Ajouter une méthode" → "Mot de passe d'application"
4. Donnez-lui un nom (ex. "Agent ADH") et copiez le mot de passe généré

### Étape 5 — Configurer les destinataires

Ouvrez `config/criteria.yaml` et modifiez la section `email > destinataires` :
```yaml
email:
  destinataires:
    - "alice@adh-consulting.fr"
    - "bob@adh-consulting.fr"
```

### Étape 6 — Ajouter vos CVs

Déposez vos CVs (format PDF ou Word .docx) dans le dossier `cvs/`.
Nommez-les avec le nom du candidat (ex. `Jean_Dupont.pdf`).
L'agent les indexera automatiquement à chaque exécution.

### Étape 7 — Tester

```bash
python -m src.main
```

Vérifiez que tout fonctionne : un email doit arriver dans votre boîte.

### Étape 8 — Automatiser (exécution chaque matin)

L'automatisation est gérée par **GitHub Actions**, inclus gratuitement avec GitHub.

1. Poussez le projet sur GitHub (il doit y être si vous avez cloné ce dépôt)
2. Allez dans **Settings > Secrets and variables > Actions** de votre dépôt GitHub
3. Ajoutez ces secrets (bouton "New repository secret") :
   - `ANTHROPIC_API_KEY`
   - `EMAIL_EXPEDITEUR`
   - `EMAIL_MOT_DE_PASSE`
4. L'agent se lancera automatiquement à 07h00 du lundi au vendredi

---

## Modifier les critères sans toucher au code

Tout se passe dans `config/criteria.yaml`.

**Ajouter un profil recherché :**
```yaml
profils:
  - "chef de projet"
  - "business analyst"
  - "votre nouveau profil ici"   # ajoutez simplement une ligne
```

**Exclure un nouveau mot-clé :**
```yaml
mots_cles:
  exclus:
    - "stage"
    - "alternance"
    - "votre mot exclu"
```

**Changer le seuil de qualité IA (0-100) :**
```yaml
seuils:
  score_ia_minimum: 70   # Plus strict (défaut: 60)
```

---

## Ajouter un CV manuellement

1. Récupérez le CV en PDF ou Word (.docx)
2. Copiez-le dans le dossier `cvs/`
3. Nommez-le avec le prénom et nom du candidat (ex. `Marie_Martin.pdf`)
4. C'est tout — l'agent le prendra en compte dès sa prochaine exécution

---

## Sources couvertes

| Source | Type | Fiabilité |
|--------|------|-----------|
| BOAMP | Appels d'offres publics | Excellente (API officielle) |
| APEC | CDI/CDD cadres | Bonne |
| Indeed France | CDI/CDD/Freelance | Moyenne (peut être bloqué) |
| Welcome to the Jungle | CDI/CDD | Bonne |
| Freelance.com | Missions freelance | Bonne |

Si une source retourne 0 résultats plusieurs jours de suite, désactivez-la dans
`config/sources.yaml` en mettant `active: false`.

---

## Architecture technique

| Composant | Solution choisie | Coût | Pourquoi |
|-----------|-----------------|------|----------|
| Scheduling | GitHub Actions | Gratuit | Inclus dans GitHub, simple |
| Stockage | SQLite | Gratuit | Aucun serveur nécessaire |
| Scraping | Python requests + BeautifulSoup | Gratuit | Standard, robuste |
| BOAMP | API REST officielle | Gratuit | Source officielle, fiable |
| Filtre passe 1 | Mots-clés / regex | Gratuit | Élimine 75% des offres sans IA |
| Filtre passe 2 | Claude Haiku (Anthropic) | ~€0.001/offre | Le moins cher du marché |
| Matching CV | TF-IDF (scikit-learn) | Gratuit | Suffisant pour comparer des CVs |
| Email | SMTP Microsoft 365 | Gratuit | Déjà inclus dans votre abonnement |
