# Veille glaucome

Outil de veille scientifique et concurrentielle sur le **glaucome** et l'**hypertension oculaire**,
consultable en local et publié sur **GitHub Pages**. Sources publiques et gratuites :

| Source | Ce qu'elle apporte |
|---|---|
| [ClinicalTrials.gov](https://clinicaltrials.gov) | Essais : phase déclarée, statut, promoteur, bras de l'étude, résultats déposés |
| [PubMed](https://pubmed.ncbi.nlm.nih.gov) | Publications biomédicales : résumé, type de publication, NCT déclarés |
| [OpenAlex](https://openalex.org) | Publications absentes de PubMed, institutions normalisées, financeurs, accès au texte |
| [Crossref](https://www.crossref.org) | Financeurs déclarés par l'éditeur (justification des financements) |
| [BDPM](https://base-donnees-publique.medicaments.gouv.fr) | France : AMM, avis HAS (SMR, ASMR), taux de remboursement, prix |
| [EMA](https://www.ema.europa.eu/en/medicines/download-medicine-data) | Union européenne : médicaments autorisés en procédure centralisée et dates |
| [openFDA](https://open.fda.gov/apis/drug/drugsfda/) | États-Unis : approbations FDA (marques NDA, génériques ANDA) et dates |

La page **Accès au marché** croise ces trois dernières sources pour les molécules de
`config/marche.ini` (collecte : `python collecter_marche.py`, lancée aussi par `mise_a_jour.py`).

**Résumés IA** : `python resumer_ia.py` produit, pour chaque nouvelle étude, 3 lignes en français et une ligne
« Pour un chef de produit », via Google Gemini (offre gratuite, clé `GEMINI_API_KEY` dans .env ou les Secrets du dépôt ; Mistral possible avec `MISTRAL_API_KEY`). GitHub Models, utilisé au départ, a fermé le 30/07/2026.
Chaque résumé est marqué « Résumé généré par IA, à vérifier » ; sans jeton, l'étape est sautée.

## Site en ligne (GitHub Pages)

Le dépôt est **public** pour publier gratuitement le site avec GitHub Pages. Il ne contient que des données
publiques ; aucune clé n'est écrite dans le code (les clés vont dans les *Secrets* GitHub).
Réglage unique : *Settings > Pages > Source = GitHub Actions*. La publication se fait après chaque mise à jour
quotidienne (`veille-quotidienne.yml`) et à chaque envoi qui modifie `site/` (`publier-site.yml`).
Adresse publique (sitemap, partage) : `config/site.ini`.

## Tests

```
pip install -r requirements-dev.txt
python -m pytest -q
```

## Consulter le site

Double-cliquez sur **`ouvrir_site.bat`** : le site s'ouvre dans votre navigateur à l'adresse
`http://127.0.0.1:8766`, accessible uniquement depuis cet ordinateur. Pour l'arrêter, fermez
la fenêtre « Serveur veille glaucome ». (Double-cliquer sur `site/index.html` fonctionne aussi.)

Pages : **Accueil** (chiffres, nouveautés de la dernière mise à jour, rubriques),
**Études** (filtres, résumés des sources, regroupement par rubrique : médicaments et dispositifs
d'abord), **Laboratoires** (promoteur / financeur / affiliation, toujours séparés), et une
**fiche détaillée** par essai et par article PubMed, avec le bouton « Copier pour Claude / ChatGPT ».

## Mettre à jour

```
python mise_a_jour.py        collecte les nouveautés depuis la dernière exécution, puis reconstruit le site
python construire_site.py    reconstruit seulement le site (aucun appel réseau)
```

La mise à jour ne collecte que ce qui est nouveau ou modifié depuis la précédente exécution
(pas d'historique ancien). Une source en panne n'empêche pas les autres ; la date de reprise
n'avance que si ClinicalTrials.gov et PubMed ont répondu.

## Mise à jour automatique (même ordinateur éteint)

Un ordinateur éteint ne peut rien exécuter : la collecte quotidienne tourne donc sur les
serveurs de **GitHub Actions**, dans un **dépôt personnel privé** (séparé du projet du professeur).

1. Chaque jour vers 7 h 30 (heure de Paris en été), GitHub démarre une machine temporaire,
   récupère le dépôt, lance `mise_a_jour.py`, puis **enregistre les nouveautés dans le dépôt**
   (`data/historique/`, `site/data/`, `site/fiches/`) et détruit la machine. L'historique est
   ainsi conservé d'un jour à l'autre, dans le dépôt privé, avec tout l'historique Git.
2. Votre ordinateur, lui, ne fait rien tant qu'il est éteint. Au démarrage, double-cliquez sur
   **`recuperer_mises_a_jour.bat`** (ou programmez-le à l'ouverture de session) : il télécharge
   les nouveautés des jours manqués, puis `ouvrir_site.bat` les affiche.
3. Si GitHub est indisponible un jour, la mise à jour suivante reprend à la dernière date réussie.

Programme : `.github/workflows/veille-quotidienne.yml` (bouton « Run workflow » pour lancer à la main).
Quand l'automatisation est active, **ne lancez plus `mise_a_jour.py` sur le PC** : récupérez seulement.

## Structure

Architecture détaillée : [docs/architecture.md](docs/architecture.md) (schéma : `docs/architecture.svg`).

```
Veille-glaucome/
├── mise_a_jour.py        ← pipeline : 11 sources publiques → SQLite → export JSON contrôlé → site → alertes
├── resumer_ia.py         ← IA traçable (Gemini ou Mistral) : résumé + catégorie fermée, JSON validé
├── construire_site.py    ← export JSON (après contrôles qualité) + fiches, depuis la base
├── demo_alerte.py        ← démo : simule un changement d'essai et montre l'alerte (sur une copie)
├── migrer_vers_sqlite.py ← migration unique de l'ancien historique JSON vers SQLite
├── collecter_marche.py   ← accès au marché (BDPM, EMA, openFDA) en autonome
├── ouvrir_site.bat       ← ouvre le site local (http://127.0.0.1:8766)
├── config/               ← réglages sans code (recherches, rubriques, molécules, site)
│   └── prompts/          ← prompts IA VERSIONNÉS (resume_classification_v1.md…)
├── veille/
│   ├── reseau.py         ← appels HTTP robustes : timeout, backoff, 429/Retry-After, logs
│   ├── base.py           ← SQLite : schéma, déduplication, versions, événements, journal
│   ├── export.py         ← contrôles qualité + export site/data/*.json
│   ├── alertes.py        ← alertes dédupliquées (alertes.md, page, e-mail optionnel)
│   ├── resumer_ia.py     ← IA : validation stricte, traçabilité
│   └── sources/          ← un connecteur par source
├── data/veille.db        ← LA BASE (versionnée)
├── data/logs/            ← journaux datés (non versionnés ; gardés 30 jours sur GitHub)
├── eval/                 ← jeu étiqueté (30 articles) + evaluer.py (matrice de confusion, F1 macro)
├── tests/                ← 94 tests pytest (lancés avant toute publication)
├── demo/                 ← kit de démo hors ligne (base, logs d'une exécution réussie, alerte test)
├── docs/                 ← architecture
├── site/                 ← tableau de bord statique (lit site/data/*.json)
└── .github/workflows/    ← tests → collecte → IA → export → GitHub Pages
```

## Principes de la veille

- **Phases** : uniquement la phase déclarée par la source, sinon « Non applicable (déclaré) » ou « Non renseignée ».
- **Niveau de preuve** : essai enregistré, protocole publié, résultats déposés au registre, publication de résultats.
- **Rôles** : pour un essai, bras déclarés au registre ; pour un article, rôle **suggéré, à vérifier** (règle sur le titre).
- **Promoteur, financeur, affiliation** : toujours séparés ; chaque financeur a sa notice justificative.
- **Classements automatiques** (rubriques, étiquettes, regroupement des laboratoires) : signalés comme tels, règles modifiables dans `config/`.
- **Aucune synthèse rédigée par une IA** : les fiches extraient les faits ; la synthèse passe par « Copier pour Claude / ChatGPT ».

## Limites connues

- **OpenAlex sans clé** : le budget gratuit est **partagé par tous les utilisateurs d'une même adresse IP**
  (réseau de l'université, ou machines de GitHub). Quand il est épuisé, l'enrichissement et la découverte
  OpenAlex sont reportés (réessai pendant 30 jours) ; les autres sources continuent.
- Les extraits des sources restent en anglais.

## Sécurité

- Aucune clé dans le code : les clés éventuelles vont dans `.env` (ignoré par Git) ou dans les *Secrets* GitHub.
- `.gitignore` exclut `.env`, les documents internes (`.docx`, `.xlsx`, `.pptx`, `.pdf`, `.msg`) et `data/local/`.
- Seules des données publiques sont versionnées.

## Dépannage

- `recuperer_mises_a_jour.bat` échoue : vérifiez la connexion ; si des fichiers ont été modifiés localement
  (par exemple en lançant `mise_a_jour.py` sur le PC), annulez-les avec `git checkout -- data site` puis relancez.
- Le site est vide : lancez `python construire_site.py`.
