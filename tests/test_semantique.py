"""Index de similarité, embeddings incrémentaux, recherche hybride (sans télécharger de modèle : encodeur simulé)."""
import numpy as np

from conftest import essai
from veille import base, semantique


class FauxEncodeur:
    """Encodeur déterministe : un vecteur par mot-clé reconnu (assez pour tester l'ordre des résultats)."""
    modele = "faux-modele"
    MOTS = ["preservative", "laser", "netarsudil", "surgery"]

    def __init__(self):
        self.appels = 0

    def encoder(self, textes):
        self.appels += len(textes)
        v = np.array([[1.0 + (m in t.lower()) * 5 for m in self.MOTS] for t in textes], dtype=np.float32)
        return v / np.linalg.norm(v, axis=1, keepdims=True)

    def question(self, texte):
        return self.encoder([texte])[0]


def index_simple():
    v = np.eye(3, dtype=np.float32)
    return semantique.Index(v, ["A", "B", "C"], [{"titre": t, "texte": t} for t in ("a", "b", "c")])


def test_index_renvoie_le_plus_proche_en_premier():
    res = index_simple().rechercher([0.1, 0.9, 0.2], k=2)
    assert [r["id"] for r in res] == ["B", "C"] and res[0]["score"] >= res[1]["score"]


def test_index_enregistrer_puis_charger(tmp_path):
    index_simple().enregistrer(tmp_path)
    recharge = semantique.Index.charger(tmp_path)
    assert recharge.ids == ["A", "B", "C"] and recharge.rechercher([1, 0, 0], k=1)[0]["id"] == "A"


def test_quantification_int8_erreur_faible():
    rng = np.random.default_rng(0)
    v = rng.normal(size=(20, 384)).astype(np.float32)
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    q, e = semantique.quantifier(v)
    assert q.dtype == np.int8 and np.abs(q * e[:, None] - v).max() < 0.01


def test_embeddings_incrementaux(conn):
    base.enregistrer_essai(conn, essai("NCT00000001", titre="Preservative-free drops", resume_source="x"), "2026-11-01")
    base.enregistrer_essai(conn, essai("NCT00000002", titre="Laser trabeculoplasty", resume_source="y"), "2026-11-01")
    enc = FauxEncodeur()
    assert semantique.mettre_a_jour(conn, enc) == 2
    assert semantique.mettre_a_jour(conn, enc) == 0          # rien n'a changé : pas de ré-encodage
    base.enregistrer_essai(conn, essai("NCT00000002", titre="Laser trabeculoplasty", resume_source="nouveau texte"), "2026-11-02")
    assert semantique.mettre_a_jour(conn, enc) == 1          # seul le document modifié est ré-encodé
    modeles = {r["modele"] for r in conn.execute("SELECT modele FROM embeddings")}
    assert modeles == {"faux-modele"}


def test_glossaire_etend_la_question():
    etendue, termes = semantique.etendre("collyres sans conservateur", {"sans conservateur": ["preservative-free"],
                                                                       "conservateur": ["preservative"], "collyres": ["eye drops"]})
    # le terme le plus long gagne : « sans conservateur » est traduit, « conservateur » n'est pas compté deux fois
    assert termes == ["preservative-free", "eye drops"] and "preservative-free" in etendue


def test_idf_favorise_les_termes_rares():
    poids = semantique.poids_idf(["trial", "preservative-free"], ["trial a", "trial b", "trial c preservative-free"])
    assert poids["preservative-free"] > poids["trial"]


def test_recherche_hybride_bonus_lexical(conn):
    base.enregistrer_essai(conn, essai("NCT00000001", titre="Preservative-free latanoprost", resume_source="eye drops"), "2026-11-01")
    base.enregistrer_essai(conn, essai("NCT00000002", titre="Selective laser trabeculoplasty", resume_source="laser"), "2026-11-01")
    enc = FauxEncodeur()
    semantique.mettre_a_jour(conn, enc)
    index = semantique.construire_index(conn, dossier=conn.execute("PRAGMA database_list").fetchone()[2] + ".index")
    res, etendue = semantique.rechercher(index, enc, "collyre sans conservateur", k=2,
                                         glossaire={"sans conservateur": ["preservative-free"]})
    assert res[0]["id"] == "NCT00000001" and res[0]["score_lexical"] == 1.0
    assert res[0]["score"] == round(res[0]["score_dense"] + semantique.POIDS_LEXICAL, 4)
