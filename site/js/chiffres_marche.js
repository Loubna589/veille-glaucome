/* Chiffres de marché publics (Open Medic pour la France, Medicare Part D pour les États-Unis).
   Lit data/chiffres_marche.json (collecter_chiffres_marche.py) et remplit la section #chiffres-marche de marche.html.
   Pour retirer cette partie : supprimer la section de marche.html et la balise <script> de ce fichier. */
(function () {
  var V = window.Veille, zone = document.getElementById("chiffres-marche");
  if (!V || !zone) return;
  var esc = V.esc, NB_SERIES = 7;
  var TYPES_FR = [["princeps", "Princeps (médicament d'origine)"], ["generiques", "Génériques"],
    ["hors_repertoire", "Hors répertoire des génériques"]];
  var PRESC = [["ophtalmologues", "Ophtalmologues libéraux"], ["generalistes", "Médecins généralistes libéraux"],
    ["autres", "Autres prescripteurs ou non précisé"]];

  function fmt(n) { return Math.round(n).toLocaleString("fr-FR"); }
  function millions(n, unite) { return (n / 1e6).toLocaleString("fr-FR", { maximumFractionDigits: n >= 1e8 ? 0 : 1 }) + " M" + (unite || ""); }
  function pct(a, b) { return b ? (100 * a / b).toLocaleString("fr-FR", { maximumFractionDigits: 1 }) + " %" : "–"; }
  function joli(lib) { return lib.charAt(0) + lib.slice(1).toLowerCase(); }
  function couleur(i) { return i < 0 ? "var(--s-autres)" : "var(--s" + (i + 1) + ")"; }
  function legende(items) {
    return '<div class="cm-legende">' + items.map(function (it) {
      return '<span><i style="background:' + it[1] + '"></i>' + esc(it[0]) + "</span>";
    }).join("") + "</div>";
  }
  function selectAnnee(id, annees, choisie) {
    return '<label class="cm-annee">Année <select id="' + id + '">' + annees.slice().reverse().map(function (a) {
      return '<option' + (a === choisie ? " selected" : "") + ">" + a + "</option>";
    }).join("") + "</select></label>";
  }
  /* Barres horizontales empilées à 100 % : lignes [{nom, parts:[[valeur, couleur, libellé]]}] */
  function barres100(lignes) {
    return '<div class="cm-barres">' + lignes.map(function (l) {
      var tot = l.parts.reduce(function (s, p) { return s + p[0]; }, 0);
      return '<div class="cm-ligne"><span class="cm-nom">' + esc(l.nom) + '</span><span class="cm-pile">' +
        l.parts.filter(function (p) { return p[0] > 0; }).map(function (p) {
          return '<span tabindex="0" style="width:' + (100 * p[0] / tot) + "%;background:" + p[1] + '" data-info="' +
            esc(l.nom + " · " + p[2] + " : " + pct(p[0], tot) + " (" + fmt(p[0]) + " boîtes)") + '"></span>';
        }).join("") + "</span></div>";
    }).join("") + "</div>";
  }
  /* Barres simples : lignes [{nom, valeur, couleur, texte, info}] */
  function barres(lignes) {
    var max = Math.max.apply(null, lignes.map(function (l) { return l.valeur; })) || 1;
    return '<div class="cm-barres">' + lignes.map(function (l) {
      return '<div class="cm-ligne"><span class="cm-nom">' + esc(l.nom) + '</span><span class="cm-piste"><span tabindex="0" style="width:' +
        (100 * l.valeur / max) + "%;background:" + l.couleur + '" data-info="' + esc(l.info) + '"></span></span><span class="cm-val">' +
        esc(l.texte) + "</span></div>";
    }).join("") + "</div>";
  }
  /* Courbes de l'évolution : series [{nom, couleur, valeurs:{annee: n}}] */
  function courbes(annees, series, unite) {
    var L = 640, H = 260, g = 44, d = 150, h = 18, b = 28;
    var max = 0;
    series.forEach(function (s) { annees.forEach(function (a) { max = Math.max(max, s.valeurs[a] || 0); }); });
    var pas = Math.pow(10, Math.floor(Math.log10(max || 1))), haut = Math.ceil(max / pas) * pas;
    function x(i) { return g + i * (L - g - d) / (annees.length - 1); }
    function y(v) { return H - b - v * (H - b - h) / haut; }
    var svg = '<svg viewBox="0 0 ' + L + " " + H + '" class="cm-svg" role="img" aria-label="Évolution par molécule">';
    for (var k = 0; k <= 4; k++) {
      var v = haut * k / 4;
      svg += '<line x1="' + g + '" x2="' + (L - d) + '" y1="' + y(v) + '" y2="' + y(v) + '" class="cm-grille"/>' +
        '<text x="' + (g - 6) + '" y="' + (y(v) + 4) + '" class="cm-axe" text-anchor="end">' + (v / 1e6).toLocaleString("fr-FR") + " M</text>";
    }
    annees.forEach(function (a, i) {
      if (annees.length < 9 || i % 2 === 0 || i === annees.length - 1)
        svg += '<text x="' + x(i) + '" y="' + (H - 8) + '" class="cm-axe" text-anchor="middle">' + a + "</text>";
    });
    var etiquettes = [];
    series.forEach(function (s) {
      var pts = annees.map(function (a, i) { return x(i) + "," + y(s.valeurs[a] || 0); }).join(" ");
      svg += '<polyline points="' + pts + '" fill="none" stroke="' + s.couleur + '" stroke-width="2" stroke-linejoin="round"/>';
      etiquettes.push({ y: y(s.valeurs[annees[annees.length - 1]] || 0), nom: s.nom });
    });
    // étiquettes directes à droite, écartées pour ne pas se chevaucher
    etiquettes.sort(function (a, b) { return a.y - b.y; });
    etiquettes.forEach(function (e, i) { if (i && e.y - etiquettes[i - 1].y < 13) e.y = etiquettes[i - 1].y + 13; });
    etiquettes.forEach(function (e) {
      svg += '<text x="' + (L - d + 8) + '" y="' + (e.y + 4) + '" class="cm-etiq">' + esc(e.nom) + "</text>";
    });
    svg += '<line class="cm-repere" x1="0" x2="0" y1="' + h + '" y2="' + (H - b) + '" style="display:none"/>';
    annees.forEach(function (a, i) {
      var w = (L - g - d) / (annees.length - 1);
      svg += '<rect class="cm-zone" data-i="' + i + '" x="' + (x(i) - w / 2) + '" y="0" width="' + w + '" height="' + H + '" fill="transparent"/>';
    });
    return '<div class="cm-graphe" data-unite="' + esc(unite) + '">' + svg + "</svg></div>";
  }
  function brancherCourbes(conteneur, annees, series) {
    var el = conteneur.querySelector(".cm-graphe"), svg = el.querySelector("svg"), repere = svg.querySelector(".cm-repere");
    var bulle = document.createElement("div");
    bulle.className = "cm-bulle"; bulle.hidden = true; el.appendChild(bulle);
    svg.querySelectorAll(".cm-zone").forEach(function (r) {
      r.addEventListener("mouseenter", function () {
        var i = +r.getAttribute("data-i"), a = annees[i], cx = +r.getAttribute("x") + +r.getAttribute("width") / 2;
        repere.setAttribute("x1", cx); repere.setAttribute("x2", cx); repere.style.display = "";
        bulle.innerHTML = "<strong>" + a + "</strong>" + series.slice().sort(function (p, q) { return (q.valeurs[a] || 0) - (p.valeurs[a] || 0); })
          .map(function (s) { return '<div><i style="background:' + s.couleur + '"></i>' + esc(s.nom) + " : " + fmt(s.valeurs[a] || 0) + "</div>"; }).join("");
        bulle.hidden = false;
        bulle.style.left = Math.min(100 * cx / 640, 62) + "%";
      });
    });
    svg.addEventListener("mouseleave", function () { bulle.hidden = true; repere.style.display = "none"; });
  }
  function bullesBarres(conteneur) {
    var b = document.createElement("div");
    b.className = "cm-bulle cm-bulle--barre"; b.hidden = true; conteneur.appendChild(b);
    function montrer(ev) {
      var t = ev.target.closest("[data-info]"); if (!t || !conteneur.contains(t)) { b.hidden = true; return; }
      var r = t.getBoundingClientRect(), c = conteneur.getBoundingClientRect();
      b.textContent = t.getAttribute("data-info"); b.hidden = false;
      b.style.left = Math.max(0, Math.min(r.left - c.left, c.width - 260)) + "px"; b.style.top = (r.top - c.top - 34) + "px";
    }
    conteneur.addEventListener("mouseover", montrer); conteneur.addEventListener("focusin", montrer);
    conteneur.addEventListener("mouseleave", function () { b.hidden = true; });
  }

  /* ---------------- France : Open Medic ---------------- */
  function france(F) {
    var annees = Object.keys(F.annees).sort(), der = annees[annees.length - 1], prem = annees[0];
    var libelles = {};
    annees.forEach(function (a) {
      Object.keys(F.annees[a].molecules).forEach(function (k) {
        var l = F.annees[a].molecules[k].libelle; if (l && l !== k) libelles[k] = joli(l);
      });
    });
    function nom(k) { return libelles[k] || k; }
    var ordre = Object.keys(F.annees[der].molecules).sort(function (p, q) { return F.annees[der].molecules[q].boites - F.annees[der].molecules[p].boites; });
    var suivies = ordre.slice(0, NB_SERIES), indice = {};
    suivies.forEach(function (k, i) { indice[k] = i; });   // la couleur suit la molécule, jamais son rang de l'année choisie
    var series = suivies.map(function (k, i) {
      var v = {}; annees.forEach(function (a) { v[a] = (F.annees[a].molecules[k] || {}).boites || 0; });
      return { nom: nom(k), couleur: couleur(i), valeurs: v };
    });
    var autres = {}; annees.forEach(function (a) {
      autres[a] = Object.keys(F.annees[a].molecules).filter(function (k) { return !(k in indice); })
        .reduce(function (s, k) { return s + F.annees[a].molecules[k].boites; }, 0);
    });
    series.push({ nom: "Autres molécules", couleur: couleur(-1), valeurs: autres });
    var A = F.annees[der], A0 = F.annees[prem];

    var html = '<h3 class="cm-titre">France · médicaments remboursés en ville (Open Medic)</h3>' +
      '<p class="sous-titre">Classe ATC ' + esc(F.classe) + ", tous régimes d'Assurance Maladie, de " + prem + " à " + der +
      ". Source : <a href=\"" + esc(F.url) + '" target="_blank" rel="noopener">' + esc(F.source) + "</a>, licence ouverte. " +
      "Décalage d'environ un an : l'année " + der + " est la plus récente publiée. Ce sont des boîtes <strong>remboursées</strong> " +
      "délivrées en pharmacie de ville (pas les ventes à l'hôpital, pas les boîtes non remboursées).</p>" +
      '<div class="cm-tuiles">' +
      '<div class="cm-tuile"><strong>' + millions(A.boites) + "</strong><span>boîtes remboursées en " + der + "</span></div>" +
      '<div class="cm-tuile"><strong>' + (A.boites >= A0.boites ? "+" : "") + pct(A.boites - A0.boites, A0.boites) + "</strong><span>de boîtes depuis " + prem + "</span></div>" +
      '<div class="cm-tuile"><strong>' + millions(A.rem, " €") + "</strong><span>remboursés en " + der + " (" + millions(A0.rem, " €") + " en " + prem + ")</span></div>" +
      '<div class="cm-tuile"><strong>' + pct(A.prescripteurs.ophtalmologues || 0, A.boites) + "</strong><span>des boîtes prescrites par un ophtalmologue libéral en " + der + "</span></div>" +
      "</div>" +
      '<div class="encadre cm-bloc"><h4>Boîtes remboursées par molécule, ' + prem + "–" + der + "</h4>" +
      '<p class="cm-aide">Les ' + NB_SERIES + " molécules les plus remboursées en " + der + ". Survolez le graphique pour lire les chiffres d'une année.</p>" +
      legende(series.map(function (s) { return [s.nom, s.couleur]; })) + '<div id="cm-courbes">' + courbes(annees, series, "boîtes") + "</div>" +
      "<details><summary>Voir le tableau des chiffres</summary>" + tableauEvolution(annees, ordre, F, nom) + "</details></div>" +
      '<div class="cm-filtre">' + selectAnnee("cm-annee-fr", annees, der) + "</div>" +
      '<div id="cm-fr-annee"></div>';
    var bloc = document.createElement("div");
    bloc.innerHTML = html; zone.appendChild(bloc);
    brancherCourbes(bloc.querySelector("#cm-courbes"), annees, series);

    function parAnnee() {
      var a = document.getElementById("cm-annee-fr").value, X = F.annees[a];
      var cles = Object.keys(X.molecules).sort(function (p, q) { return X.molecules[q].boites - X.molecules[p].boites; });
      var parts = barres(cles.map(function (k) {
        var m = X.molecules[k];
        return { nom: nom(k), valeur: m.boites, couleur: couleur(k in indice ? indice[k] : -1), texte: pct(m.boites, X.boites),
          info: nom(k) + " : " + fmt(m.boites) + " boîtes, " + fmt(m.rem) + " € remboursés en " + a };
      }));
      var types = barres100([{ nom: "Toute la classe", parts: TYPES_FR.map(function (t, i) {
        return [cles.reduce(function (s, k) { return s + (X.molecules[k][t[0]] || 0); }, 0), "var(--s" + (i + 1) + ")", t[1]]; }) }]
        .concat(cles.slice(0, 10).map(function (k) {
          return { nom: nom(k), parts: TYPES_FR.map(function (t, i) { return [X.molecules[k][t[0]] || 0, "var(--s" + (i + 1) + ")", t[1]]; }) };
        })));
      var presc = barres100(Object.keys(F.annees).sort().map(function (an) {
        var P = F.annees[an].prescripteurs;
        return { nom: an, parts: PRESC.map(function (p, i) { return [P[p[0]] || 0, "var(--s" + (i + 1) + ")", p[1]]; }) };
      }));
      var produits = '<div class="cm-defile-simple"><table class="cm-table"><thead><tr><th>#</th><th>Produit (nom déclaré)</th><th>Molécule</th><th>Boîtes</th><th>Part</th><th>Remboursé</th></tr></thead><tbody>' +
        X.produits.map(function (p, i) {
          return "<tr><td>" + (i + 1) + "</td><td>" + esc(p.nom) + "</td><td>" + esc(nom(p.atc)) + "</td><td>" + fmt(p.boites) +
            "</td><td>" + pct(p.boites, X.boites) + "</td><td>" + fmt(p.rem) + " €</td></tr>";
        }).join("") + "</tbody></table></div>";
      var cible = document.getElementById("cm-fr-annee");
      cible.innerHTML =
        '<div class="cm-grille2">' +
        '<div class="encadre cm-bloc"><h4>Parts de marché en ' + a + " (en boîtes)</h4>" + parts + "</div>" +
        '<div class="encadre cm-bloc"><h4>Princeps, génériques et hors répertoire en ' + a + "</h4>" +
        legende(TYPES_FR.map(function (t, i) { return [t[1], "var(--s" + (i + 1) + ")"]; })) + types +
        '<p class="cm-aide">« Hors répertoire » : aucun générique inscrit au répertoire de l\'ANSM pour ce produit (souvent des unidoses ' +
        "sans conservateur ou des associations). Classement déclaré par Open Medic (champ TOP_GEN).</p></div></div>" +
        '<div class="encadre cm-bloc"><h4>Les 15 produits les plus remboursés en ' + a + "</h4>" + produits +
        '<p class="cm-aide">Toutes présentations d\'un même nom réunies (flacon, unidoses, boîtes de 1 ou 3).</p></div>' +
        '<div class="encadre cm-bloc"><h4>Qui prescrit ? Part des boîtes par prescripteur</h4>' +
        legende(PRESC.map(function (p, i) { return [p[1], "var(--s" + (i + 1) + ")"]; })) + presc + "</div>";
      cible.querySelectorAll(".cm-bloc").forEach(bullesBarres);
    }
    document.getElementById("cm-annee-fr").addEventListener("change", parAnnee);
    parAnnee();
  }
  function tableauEvolution(annees, ordre, F, nom) {
    return '<div class="cm-defile"><table class="cm-table"><thead><tr><th>Molécule (ATC)</th>' + annees.map(function (a) { return "<th>" + a + "</th>"; }).join("") +
      "</tr></thead><tbody>" + ordre.map(function (k) {
        return "<tr><td>" + esc(nom(k)) + " <small>" + esc(k) + "</small></td>" + annees.map(function (a) {
          var m = F.annees[a].molecules[k]; return "<td>" + (m ? fmt(m.boites) : "–") + "</td>";
        }).join("") + "</tr>";
      }).join("") + "</tbody></table></div>";
  }

  /* ---------------- États-Unis : Medicare Part D ---------------- */
  function usa(U) {
    var annees = U.annees, der = annees[annees.length - 1];
    var bloc = document.createElement("div");
    bloc.innerHTML = '<h3 class="cm-titre">États-Unis · Medicare Part D (CMS)</h3>' +
      '<p class="sous-titre">Dépenses et prescriptions des antiglaucomateux pour les personnes couvertes par Medicare Part D ' +
      "(surtout les plus de 65 ans), de " + annees[0] + " à " + der + ". Source : <a href=\"" + esc(U.url) + '" target="_blank" rel="noopener">' +
      esc(U.source) + "</a>, données publiques. Les dépenses sont <strong>brutes</strong>, avant les remises négociées avec les laboratoires : " +
      "ce n'est pas le chiffre d'affaires des laboratoires. Décalage d'environ un an.</p>" +
      '<div class="cm-filtre">' + selectAnnee("cm-annee-us", annees, der) + "</div><div id=\"cm-us-annee\"></div>";
    zone.appendChild(bloc);
    var COUL = { marque: "var(--s1)", generique: "var(--s2)" }, LIB = { marque: "Marque (princeps ou produit protégé)", generique: "Générique" };
    function parAnnee() {
      var a = document.getElementById("cm-annee-us").value;
      var l = U.lignes.filter(function (x) { return x.depenses[a]; }).sort(function (p, q) { return q.depenses[a] - p.depenses[a]; });
      var tot = { marque: [0, 0], generique: [0, 0] };
      l.forEach(function (x) { tot[x.type][0] += x.depenses[a]; tot[x.type][1] += x.prescriptions[a] || 0; });
      var resume = barres100([
        { nom: "Dépenses", parts: [[tot.marque[0], COUL.marque, LIB.marque], [tot.generique[0], COUL.generique, LIB.generique]] },
        { nom: "Prescriptions", parts: [[tot.marque[1], COUL.marque, LIB.marque], [tot.generique[1], COUL.generique, LIB.generique]] }])
        .replace(/ boîtes\)/g, ")");
      var top = barres(l.slice(0, 15).map(function (x) {
        return { nom: x.marque + (x.type === "generique" ? " (gén.)" : ""), valeur: x.depenses[a], couleur: COUL[x.type],
          texte: millions(x.depenses[a], " $"), info: x.marque + " · " + x.generique + " : " + fmt(x.depenses[a]) + " $ et " +
          fmt(x.prescriptions[a] || 0) + " prescriptions en " + a };
      }));
      var cible = document.getElementById("cm-us-annee");
      cible.innerHTML = '<div class="cm-grille2">' +
        '<div class="encadre cm-bloc"><h4>Marques et génériques en ' + a + "</h4>" +
        legende([[LIB.marque, COUL.marque], [LIB.generique, COUL.generique]]) + resume +
        '<p class="cm-aide">Total : ' + millions(tot.marque[0] + tot.generique[0], " $") + " de dépenses et " +
        millions(tot.marque[1] + tot.generique[1]) + " de prescriptions. Les génériques font l'essentiel des prescriptions, " +
        "les marques l'essentiel des dépenses.</p></div>" +
        '<div class="encadre cm-bloc"><h4>Les 15 médicaments aux plus fortes dépenses en ' + a + "</h4>" +
        legende([[LIB.marque, COUL.marque], [LIB.generique, COUL.generique]]) + top + "</div></div>";
      cible.querySelectorAll(".cm-bloc").forEach(bullesBarres);
    }
    document.getElementById("cm-annee-us").addEventListener("change", parAnnee);
    parAnnee();
  }

  V.charger(["chiffres_marche.json"]).then(function (r) {
    var d = r[0];
    if (d.france && Object.keys(d.france.annees || {}).length) france(d.france);
    if (d.usa && d.usa.lignes && d.usa.lignes.length) usa(d.usa);
    zone.insertAdjacentHTML("beforeend", '<p class="cm-aide">Chiffres publics et gratuits uniquement. Les données de prescription ' +
      "détaillées des sociétés d'études (IQVIA Xponent, etc.) sont payantes et sous licence : elles ne sont pas utilisées ici. " +
      "Sources vérifiées le " + esc(d.verifie_le || "") + " ; mise à jour automatique dès qu'une nouvelle année est publiée.</p>");
  }).catch(function () { zone.innerHTML += '<p class="vide">Chiffres de marché indisponibles.</p>'; });
})();
