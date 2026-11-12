"""Recherche sémantique : embeddings locaux et gratuits + index de similarité.

Modèle : intfloat/multilingual-e5-small, version ONNX quantifiée publiée par Xenova
(« Xenova/multilingual-e5-small », 118 Mo, 384 dimensions, multilingue : une question en français
retrouve des résumés en anglais). C'est EXACTEMENT le même fichier que celui utilisé par
transformers.js dans le navigateur : les vecteurs du site et ceux de Python sont compatibles.

Calcul : onnxruntime + tokenizers (pas de torch), moyenne des vecteurs de jetons (mean pooling),
normalisation L2. Convention e5 : « passage: » devant les documents, « query: » devant les questions.

Index : FAISS (IndexFlatIP, produit scalaire = cosinus sur vecteurs normalisés) quand la bibliothèque
est disponible (GitHub Actions, Linux). Sur ce PC, la stratégie de sécurité Windows bloque la DLL
de faiss-cpu : on utilise alors une recherche exacte numpy, qui donne les MÊMES résultats que
IndexFlatIP (même calcul, sans approximation).

Stockage : table SQLite `embeddings` (vecteur, modèle, date, empreinte du texte : un document n'est
ré-encodé que si son texte change) ; index sur disque dans data/index/.
"""
import base64
import json
import time
from pathlib import Path

import numpy as np

from veille import base

RACINE = Path(__file__).resolve().parents[1]
DOSSIER_INDEX = RACINE / "data" / "index"
DOSSIER_MODELES = RACINE / "data" / "local" / "modeles"
MODELE = "Xenova/multilingual-e5-small"
FICHIER_ONNX = "onnx/model_quantized.onnx"
DIMENSION = 384
LONGUEUR_MAX = 256       # jetons par document (titre + début du résumé)
LOT = 16

SCHEMA = """
CREATE TABLE IF NOT EXISTS embeddings (
    objet_id TEXT PRIMARY KEY, objet_type TEXT NOT NULL, empreinte_texte TEXT NOT NULL,
    modele TEXT NOT NULL, date TEXT NOT NULL, vecteur BLOB NOT NULL
);
"""

try:  # FAISS si disponible ; sinon recherche exacte numpy (mêmes résultats)
    import faiss  # type: ignore
except Exception:  # noqa: BLE001 — ImportError, ou DLL bloquée par la stratégie Windows (OSError)
    faiss = None


class Encodeur:
    """Encode des textes en vecteurs normalisés (384 dimensions)."""

    def __init__(self, modele=MODELE):
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer

        def fichier(nom):
            try:
                return hf_hub_download(modele, nom, cache_dir=DOSSIER_MODELES)
            except Exception:  # noqa: BLE001 — hors ligne (jour de la démo) : copie déjà téléchargée
                return hf_hub_download(modele, nom, cache_dir=DOSSIER_MODELES, local_files_only=True)

        chemin_tok, chemin_onnx = fichier("tokenizer.json"), fichier(FICHIER_ONNX)
        self.modele = modele
        self.tokenizer = Tokenizer.from_file(chemin_tok)
        self.tokenizer.enable_truncation(LONGUEUR_MAX)
        self.tokenizer.enable_padding(pad_id=self.tokenizer.token_to_id("<pad>") or 1, pad_token="<pad>")
        options = ort.SessionOptions()
        options.log_severity_level = 3
        self.session = ort.InferenceSession(chemin_onnx, options, providers=["CPUExecutionProvider"])

    def encoder(self, textes):
        sortie = []
        for i in range(0, len(textes), LOT):
            lots = self.tokenizer.encode_batch(textes[i:i + LOT])
            ids = np.array([l.ids for l in lots], dtype=np.int64)
            masque = np.array([l.attention_mask for l in lots], dtype=np.int64)
            etats = self.session.run(None, {"input_ids": ids, "attention_mask": masque,
                                            "token_type_ids": np.zeros_like(ids)})[0]
            m = masque[..., None].astype(np.float32)
            moyenne = (etats * m).sum(axis=1) / np.clip(m.sum(axis=1), 1e-9, None)
            sortie.append(moyenne / np.linalg.norm(moyenne, axis=1, keepdims=True))
        return np.vstack(sortie).astype(np.float32) if sortie else np.zeros((0, DIMENSION), np.float32)

    def question(self, texte):
        return self.encoder([f"query: {texte}"])[0]


# ------------------------------------------------------------ documents à indexer

def documents(conn):
    """(id, type, texte « passage: … », métadonnées) pour chaque essai et publication de la base."""
    docs = []
    for e in conn.execute("SELECT nct, donnees FROM essais ORDER BY nct"):
        d = json.loads(e["donnees"])
        texte = f"{d.get('titre') or ''}. {d.get('resume_source') or ''}"
        docs.append((e["nct"], "essai", texte, {"titre": d.get("titre"), "lien": d.get("lien"),
                                                "fiche": f"fiches/{e['nct']}.html", "date": d.get("date_derniere_mise_a_jour"),
                                                "texte": texte[:1200]}))
    for a in conn.execute("SELECT pmid, openalex_id, doi, origine, donnees FROM articles ORDER BY id"):
        d = json.loads(a["donnees"])
        ident = a["pmid"] if a["origine"] == "pubmed" else a["openalex_id"]
        texte = f"{d.get('titre') or ''}. {d.get('resume') or ''}"
        lien = d.get("lien") or (f"https://doi.org/{a['doi']}" if a["doi"] else None)
        docs.append((ident, "article" if a["origine"] == "pubmed" else "publication", texte,
                     {"titre": d.get("titre"), "lien": lien, "fiche": f"fiches/{ident}.html" if a["origine"] == "pubmed" else None,
                      "date": d.get("date_entree_pubmed") or d.get("date_publication"), "texte": texte[:1200]}))
    return docs


def mettre_a_jour(conn, encodeur=None):
    """Calcule les embeddings manquants ou périmés (texte modifié). Renvoie le nombre de documents encodés."""
    conn.executescript(SCHEMA)
    connus = {r["objet_id"]: (r["empreinte_texte"], r["modele"]) for r in
              conn.execute("SELECT objet_id, empreinte_texte, modele FROM embeddings")}
    a_faire = [(i, t, txt) for i, t, txt, _ in documents(conn)
               if connus.get(i) != (base.empreinte(txt), (encodeur.modele if encodeur else MODELE))]
    if not a_faire:
        return 0
    encodeur = encodeur or Encodeur()
    vecteurs = encodeur.encoder([f"passage: {txt}" for _, _, txt in a_faire])
    jour = time.strftime("%Y-%m-%d")
    conn.executemany(
        "INSERT INTO embeddings (objet_id, objet_type, empreinte_texte, modele, date, vecteur) VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(objet_id) DO UPDATE SET objet_type=excluded.objet_type, empreinte_texte=excluded.empreinte_texte, "
        "modele=excluded.modele, date=excluded.date, vecteur=excluded.vecteur",
        [(i, t, base.empreinte(txt), encodeur.modele, jour, v.astype(np.float32).tobytes())
         for (i, t, txt), v in zip(a_faire, vecteurs)])
    conn.commit()
    return len(a_faire)


# ------------------------------------------------------------ index

class Index:
    """Index de similarité cosinus : FAISS IndexFlatIP si disponible, sinon numpy (résultats identiques)."""

    def __init__(self, vecteurs, ids, metas):
        self.vecteurs = np.ascontiguousarray(vecteurs, dtype=np.float32)
        self.ids, self.metas = list(ids), list(metas)
        self.moteur = "faiss" if faiss is not None else "numpy"
        if faiss is not None:
            self.faiss = faiss.IndexFlatIP(self.vecteurs.shape[1])
            self.faiss.add(self.vecteurs)

    def rechercher(self, vecteur, k=5):
        vecteur = np.asarray(vecteur, dtype=np.float32).reshape(1, -1)
        k = min(k, len(self.ids))
        if self.moteur == "faiss":
            scores, positions = self.faiss.search(vecteur, k)
            paires = zip(positions[0], scores[0])
        else:
            scores = self.vecteurs @ vecteur[0]
            positions = np.argsort(-scores, kind="stable")[:k]
            paires = ((p, scores[p]) for p in positions)
        return [{"id": self.ids[p], "score": round(float(s), 4), **self.metas[p]} for p, s in paires]

    def enregistrer(self, dossier=DOSSIER_INDEX):
        dossier = Path(dossier)
        dossier.mkdir(parents=True, exist_ok=True)
        np.save(dossier / "vecteurs.npy", self.vecteurs)
        (dossier / "documents.json").write_text(json.dumps(
            {"modele": MODELE, "dimension": int(self.vecteurs.shape[1]), "construit_le": time.strftime("%Y-%m-%d %H:%M"),
             "moteur": self.moteur, "ids": self.ids, "metas": self.metas}, ensure_ascii=False), encoding="utf-8")
        if self.moteur == "faiss":
            faiss.write_index(self.faiss, str(dossier / "index.faiss"))

    @classmethod
    def charger(cls, dossier=DOSSIER_INDEX):
        dossier = Path(dossier)
        info = json.loads((dossier / "documents.json").read_text(encoding="utf-8"))
        return cls(np.load(dossier / "vecteurs.npy"), info["ids"], info["metas"])


def construire_index(conn, dossier=DOSSIER_INDEX):
    """Construit l'index à partir de la table embeddings (seulement les documents encore présents)."""
    metas = {i: dict(m, type=t) for i, t, _, m in documents(conn)}
    lignes = [r for r in conn.execute("SELECT objet_id, vecteur FROM embeddings ORDER BY objet_id") if r["objet_id"] in metas]
    vecteurs = np.vstack([np.frombuffer(r["vecteur"], dtype=np.float32) for r in lignes]) if lignes \
        else np.zeros((0, DIMENSION), np.float32)
    index = Index(vecteurs, [r["objet_id"] for r in lignes], [metas[r["objet_id"]] for r in lignes])
    index.enregistrer(dossier)
    return index


# ------------------------------------------------------------ recherche hybride (dense + glossaire)

FICHIER_GLOSSAIRE = RACINE / "config" / "glossaire_fr_en.ini"
POIDS_LEXICAL = 0.10   # bonus maximal quand TOUS les termes du glossaire de la question sont dans le document


def charger_glossaire(chemin=FICHIER_GLOSSAIRE):
    import configparser
    config = configparser.ConfigParser(interpolation=None, delimiters=("=",))
    config.read(chemin, encoding="utf-8")
    if not config.has_section("termes"):
        return {}
    return {k.strip().lower(): [x.strip() for x in v.split("|") if x.strip()] for k, v in config["termes"].items()}


def etendre(question, glossaire=None):
    """Ajoute à la question les traductions anglaises des termes du glossaire (les plus longs d'abord).

    Renvoie (question étendue, liste des termes anglais ajoutés)."""
    glossaire = charger_glossaire() if glossaire is None else glossaire
    reste, ajouts = question.lower(), []
    for terme in sorted(glossaire, key=len, reverse=True):
        if terme in reste:
            ajouts += [x for x in glossaire[terme] if x not in ajouts]
            reste = reste.replace(terme, " ")
    return (f"{question} ({', '.join(ajouts)})" if ajouts else question), ajouts


def poids_idf(termes, textes):
    """Poids de chaque terme selon sa rareté dans le corpus (IDF) : un terme rare est plus discriminant."""
    import math
    n = max(len(textes), 1)
    textes = [(t or "").lower() for t in textes]
    return {t: math.log((n + 1) / (sum(1 for x in textes if t.lower() in x) + 1)) + 1e-6 for t in termes}


def score_lexical(texte, termes, poids=None):
    """Part (pondérée par IDF) des termes du glossaire présents dans le texte du document, entre 0 et 1."""
    if not termes:
        return 0.0
    poids = poids or {t: 1.0 for t in termes}
    texte = (texte or "").lower()
    return sum(poids[t] for t in termes if t.lower() in texte) / sum(poids[t] for t in termes)


def rechercher(index, encodeur, question, k=5, glossaire=None):
    """Recherche hybride : score = cosinus(question étendue, document) + POIDS_LEXICAL × score lexical (IDF).

    Renvoie (résultats, question étendue). Chaque résultat garde ses deux composantes de score."""
    etendue, termes = etendre(question, glossaire)
    poids = poids_idf(termes, [m.get("texte") for m in index.metas])
    # Corpus de quelques milliers de documents : on note TOUS les documents (calcul exact, < 10 ms)
    candidats = index.rechercher(encodeur.question(etendue), k=len(index.ids))
    for r in candidats:
        r["score_dense"] = r["score"]
        r["score_lexical"] = round(score_lexical(r.get("texte"), termes, poids), 3)
        r["score"] = round(r["score_dense"] + POIDS_LEXICAL * r["score_lexical"], 4)
    candidats.sort(key=lambda r: -r["score"])
    return candidats[:k], etendue


# ------------------------------------------------------------ export pour le site (recherche dans le navigateur)

def quantifier(vecteurs):
    """int8 par vecteur, avec une échelle par ligne : 4 fois plus léger, erreur de score < 0,01."""
    echelles = np.abs(vecteurs).max(axis=1, keepdims=True) / 127.0
    echelles[echelles == 0] = 1.0
    return np.round(vecteurs / echelles).astype(np.int8), echelles[:, 0].astype(np.float32)


def exporter_site(index, chemin):
    q, echelles = quantifier(index.vecteurs)
    contenu = {"modele": MODELE, "dimension": int(index.vecteurs.shape[1]), "prefixe_question": "query: ",
               "quantification": "int8 par vecteur (valeur = octet × echelle)", "ids": index.ids,
               "poids_lexical": POIDS_LEXICAL, "glossaire": charger_glossaire(),
               "metas": [{k: m.get(k) for k in ("titre", "type", "fiche", "lien", "date", "texte")} for m in index.metas],
               "echelles": [round(float(e), 8) for e in echelles],
               "vecteurs_int8_base64": base64.b64encode(q.tobytes()).decode("ascii")}
    Path(chemin).write_text(json.dumps(contenu, ensure_ascii=False), encoding="utf-8")
    return Path(chemin).stat().st_size
