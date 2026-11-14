# Architecture de la veille glaucome

Chaîne de traitement, de la collecte à la publication. Le même schéma existe en image : [architecture.svg](architecture.svg).

```mermaid
flowchart LR
    subgraph API["11 sources publiques : 4 scientifiques + 7 réglementaires"]
        CT[ClinicalTrials.gov<br/>essais]
        PM[PubMed<br/>articles]
        OA[OpenAlex<br/>hors PubMed]
        CR[Crossref<br/>financeurs]
        BD[BDPM<br/>France]
        EM[EMA<br/>UE]
        FD[openFDA<br/>USA]
        CA[Santé Canada<br/>Canada]
        ES[AEMPS CIMA<br/>Espagne]
        IT[AIFA<br/>Italie]
        CH[Swissmedic<br/>Suisse]
    end

    subgraph GHA["GitHub Actions — chaque jour 5 h 30 UTC"]
        T[pytest<br/>94 tests] --> P
        P["Python : mise_a_jour.py<br/>reseau.py : timeout, backoff, 429/Retry-After, logs"]
    end

    API --> P
    P --> DB[("SQLite data/veille.db<br/>articles · essais · versions_essais<br/>evenements · executions · traitements_ia")]
    DB --> IA["IA Gemini (gratuit)<br/>JSON validé · catégories fermées<br/>prompt versionné · non vérifié"]
    IA --> DB
    DB --> Q{"Contrôles qualité<br/>champs · dates · doublons"}
    Q -->|valide| J["Export JSON<br/>site/data/*.json"]
    Q -->|rejet| R[qualite.json]
    J --> GP["GitHub Pages<br/>tableau de bord statique"]
    DB --> AL["Alertes dédupliquées<br/>alertes.md · page Alertes · e-mail optionnel"]

    subgraph INT["Couche « intelligence »"]
        EM2["Embeddings<br/>multilingual-e5-small ONNX q8<br/>table embeddings"] --> IX["Index FAISS IndexFlatIP<br/>ou numpy (identique)"]
        IX --> RH["Recherche hybride<br/>cosinus + glossaire FR→EN (IDF)<br/>CLI chercher.py · navigateur transformers.js"]
        RH --> RAG["Assistant RAG (Flask local)<br/>Gemini · prompt rag_v1<br/>citations vérifiées · journal echanges_rag"]
        CA["Carte Cytoscape.js<br/>liens déclarés par les sources"]
        PF["Performances<br/>F1 macro · précision@5 · MRR"]
    end
    DB --> EM2
    DB --> CA
    J --> GP
```

## Rôle de chaque brique

| Brique | Fichier(s) | Ce qu'elle garantit |
|---|---|---|
| Connecteurs | `veille/sources/*.py` | un module par source, données normalisées, « on n'invente rien » |
| Réseau robuste | `veille/reseau.py` | timeout, tentatives limitées, backoff exponentiel, 429 + Retry-After, logs `data/logs/` |
| Orchestration | `mise_a_jour.py` | une étape par source ; une panne → exécution **partielle**, pas d'arrêt |
| Stockage | `veille/base.py`, `data/veille.db` | déduplication par clés uniques (PMID, DOI, OpenAlex, NCT), versions, événements, journal |
| IA traçable | `veille/resumer_ia.py`, `config/prompts/` | sortie JSON validée, modèle + version du prompt + date + statut de validation |
| Évaluation | `eval/jeu_etiquete.csv`, `eval/evaluer.py` | matrice de confusion, F1 macro sur 30 articles étiquetés à la main |
| Contrôles qualité | `veille/export.py` | aucune donnée invalide publiée ; rejets listés dans `qualite.json` |
| Alertes | `veille/alertes.py` | un événement = une alerte, jamais deux fois |
| Embeddings + index | `veille/semantique.py`, `data/index/` | modèle local gratuit, incrémental ; FAISS ou numpy (résultats identiques) |
| Recherche | `chercher.py`, `site/recherche.html` | hybride (cosinus + glossaire IDF), score détaillé, même modèle en Python et dans le navigateur |
| Assistant RAG | `assistant.py`, `veille/rag.py`, `config/prompts/rag_v1.md` | réponse uniquement depuis les extraits ; citations vérifiées ; journal |
| Carte | `veille/graphe.py`, `site/carte.html` | aucun lien déduit : uniquement des données déclarées |
| Performances | `eval/`, `site/performances.html` | F1 macro, précision@5, MRR sur jugements humains |
| Tests | `tests/` | 94 tests ; bloquent la publication en cas d'échec |
| Publication | `.github/workflows/` | tests → collecte → IA → export → commit → GitHub Pages |
