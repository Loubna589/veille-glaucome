# Schéma « Comment ça marche » (site/img/architecture.svg) : python docs/schema_architecture.py le régénère
W, H = 1240, 780
out = []
def t(x, y, s, cls="txt", anchor="start"):
    s = s.replace("&", "&amp;").replace("<", "&lt;")
    out.append(f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}">{s}</text>')
def boite(x, y, w, h, coul, num, titre, lignes, fond="#ffffff"):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{fond}" stroke="{coul}" stroke-width="2"/>')
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="38" rx="14" fill="{coul}"/><rect x="{x}" y="{y+24}" width="{w}" height="14" fill="{coul}"/>')
    if num:
        out.append(f'<circle cx="{x+20}" cy="{y+19}" r="11" fill="#fff"/>')
        t(x+20, y+24, num, "num", "middle")
    t(x + (38 if num else 14), y+25, titre, "ttl")
    for i, l in enumerate(lignes):
        t(x+14, y+60+i*19, l, "gras" if l in ("Recherche :", "Autorités de santé :", "Chiffres de marché :") else "txt")
def fleche(x1, y1, x2, y2):
    out.append(f'<path d="M{x1},{y1} L{x2},{y2}" class="fl"/>')

out.append(f'<rect width="{W}" height="{H}" fill="#f4f7fb"/>')
t(28, 42, "Glaucoma Intelligence : comment le site se construit tout seul, chaque jour", "h1")
t(28, 66, "Un robot (GitHub Actions) lance le programme Python ; si un test échoue, rien n'est publié et l'ancienne version du site reste en ligne.", "sous")

# 1. Sources
boite(28, 92, 250, 372, "#0b4f8a", "1", "Les sources officielles", [
    "Recherche :", "ClinicalTrials.gov · PubMed", "OpenAlex · Crossref", "",
    "Autorités de santé :", "BDPM (France) · EMA (UE)", "FDA (USA) · Santé Canada", "AEMPS (Espagne) · AIFA (Italie)", "Swissmedic (Suisse)", "",
    "Chiffres de marché :", "Open Medic (France)", "Medicare Part D (USA)", "", "+ accès libre : PubMed Central"])
# 2. Robot
boite(318, 92, 250, 210, "#0b7a73", "2", "Le robot quotidien", [
    "GitHub Actions + Python", "1. 130 tests automatiques", "2. collecte des nouveautés", "3. une source en panne", "    n'arrête pas les autres", "4. tout est journalisé"])
# 3. Base
boite(318, 334, 250, 130, "#3f3c9e", "3", "La base de données", [
    "SQLite : essais, articles,", "versions des essais, alertes,", "journal, sorties de l'IA"])
# 4. IA
boite(608, 92, 290, 210, "#c2410c", "4", "L'IA : Gemini (Google)", [
    "• résume chaque article en 3 lignes", "• le classe dans une catégorie", "• prépare les réponses de l'assistant", "• écrit les 5 points de la semaine", "Chaque sortie garde : quelle IA,", "quelle consigne, quelle date."])
# 5. Contrôles
boite(608, 334, 290, 130, "#8a5300", "5", "Les contrôles qualité", [
    "champs obligatoires, dates valides,", "pas de doublon (PMID, DOI, NCT) ;", "les rejets sont listés, pas publiés"])
# 6. Site
boite(938, 92, 274, 372, "#146c43", "6", "Le site (GitHub Pages)", [
    "Cette semaine (5 points)", "Rechercher (par le sens)", "Assistant (bulle, voix)", "Essais & articles", "  + qualité de l'étude", "  + accès à l'article entier", "Laboratoires (fiches)", "Autorisations & remboursement", "  + chiffres de marché", "Alertes", "Méthode et limites · À propos"])
fleche(278, 200, 314, 200); fleche(443, 302, 443, 330); fleche(568, 200, 604, 200); fleche(568, 400, 604, 400)
fleche(753, 302, 753, 330); fleche(898, 400, 934, 400)

# Sorties
t(28, 510, "Ce qui en sort, sans intervention", "h2")
sorties = [
    ("#0b4f8a", "Alertes", ["nouvel essai, changement de", "statut, de date, résultats :", "jamais signalé deux fois"]),
    ("#c2410c", "E-mail de la semaine", ["les 5 points + les alertes,", "tous les 7 jours, par Gmail", "et par une issue GitHub"]),
    ("#146c43", "Fiches laboratoires", ["produits par pays (nom", "commercial, molécule), essais", "et actualités"]),
    ("#3f3c9e", "Accès aux articles", ["libre ou payant ; boutons :", "texte gratuit, auteur,", "ResearchGate, BU"]),
    ("#0b7a73", "Chiffres de marché", ["boîtes remboursées (France),", "dépenses Medicare (USA),", "mis à jour chaque année"]),
]
for i, (c, ti, li) in enumerate(sorties):
    x = 28 + i * 240
    boite(x, 526, 226, 128, c, "", ti, li)
t(28, 690, "Recherche « par le sens » : un petit modèle, sur la machine, transforme chaque texte en empreinte de sens ;", "sous")
t(28, 710, "une question en français retrouve un article en anglais qui parle de la même chose. L'assistant ne répond qu'avec les articles trouvés, et les cite.", "sous")
t(28, 742, "Code ouvert : github.com/Loubna589/veille-glaucome · projet pédagogique, M2 MOD, IAE Clermont Auvergne", "mini")

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="Inter, Segoe UI, system-ui, sans-serif" role="img" aria-labelledby="t d">
<title id="t">Comment Glaucoma Intelligence se construit chaque jour</title>
<desc id="d">Sources officielles, robot GitHub Actions et tests, base SQLite, IA Gemini, contrôles qualité, site GitHub Pages ; sorties : alertes, e-mail de la semaine, fiches concurrents, accès aux articles, chiffres de marché.</desc>
<defs><marker id="f" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#52627a"/></marker>
<style>.h1{{font-size:21px;font-weight:800;fill:#0f1d33}}.h2{{font-size:16px;font-weight:800;fill:#0f1d33}}.sous{{font-size:13px;fill:#52627a}}.mini{{font-size:11.5px;fill:#52627a}}
.ttl{{font-size:14.5px;font-weight:700;fill:#fff}}.num{{font-size:12px;font-weight:800;fill:#0f1d33}}.txt{{font-size:12.5px;fill:#33425a}}.gras{{font-size:12.5px;font-weight:700;fill:#0f1d33}}
.fl{{stroke:#52627a;stroke-width:2;fill:none;marker-end:url(#f)}}</style></defs>
{chr(10).join(out)}
</svg>'''
open(__import__("pathlib").Path(__file__).resolve().parents[1] / "site" / "img" / "architecture.svg", "w", encoding="utf-8").write(svg)
