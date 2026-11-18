from veille.sources import chiffres_marche as cm

ENTETE = "ATC1;l_ATC1;ATC2;L_ATC2;ATC3;L_ATC3;ATC4;L_ATC4;ATC5;L_ATC5;CIP13;l_cip13;TOP_GEN;GEN_NUM;age;sexe;BEN_REG;PSP_SPE;BOITES;REM;BSE"


def ligne(atc4, atc5, lib, cip, top, spe, boites, rem):
    return f"S;x;S01;x;S01E;x;{atc4};x;{atc5};{lib};3400000000000;{cip};{top};0;0;1;11;{spe};{boites};{rem};0"


def test_agregation_open_medic_classe_s01e_seulement():
    lignes = [ENTETE,
              ligne("S01EE", "S01EE01", "LATANOPROST", "XALATAN 0,005% COLLYRE FL", "4", "15", "10", "100,50"),
              ligne("S01EE", "S01EE01", "LATANOPROST", "LATANOPROST VIATRIS 0,005% COLLYRE", "1", "1", "30", "90"),
              ligne("S01EE", "S01EE01", "LATANOPROST", "MONOPROST 0,005% COLLYRE UNIDOSE 30", "0", "90", "60", "1 200,00"),
              ligne("S01XA", "S01XA20", "LARMES", "LARMES 10ML", "0", "15", "999", "1")]
    r = cm.agreger_open_medic(lignes)
    m = r["molecules"]["S01EE01"]
    assert r["boites"] == 100 and m["princeps"] == 10 and m["generiques"] == 30 and m["hors_repertoire"] == 60
    assert m["rem"] == 1390 and m["libelle"] == "LATANOPROST"
    assert r["prescripteurs"] == {"ophtalmologues": 10, "generalistes": 30, "autres": 60}
    assert [p["nom"] for p in r["produits"]] == ["MONOPROST", "LATANOPROST VIATRIS", "XALATAN"]


def test_nom_produit_et_nombres():
    assert cm.nom_produit("BRINZOLAMIDE/TIM VTS 10/5MG/ML COLL") == "BRINZOLAMIDE/TIM VTS"
    assert cm.nom_produit("AZOPT 10MG/ML COLLYRE FL 5ML (ADP2)") == "AZOPT"
    assert cm.nom_produit("SIMBRINZA COLLYRE") == "SIMBRINZA" and cm.nom_produit("Dualkopt collyre 1") == "DUALKOPT"
    assert cm.nombre("1 234,56") == 1234.56 and cm.nombre("") == 0


def test_medicare_marque_generique_et_hors_glaucome():
    csv = ("Brnd_Name,Gnrc_Name,Tot_Mftr,Mftr_Name,Tot_Spndng_2023,Tot_Clms_2023,Tot_Spndng_2024,Tot_Clms_2024\n"
           "Lumigan,Bimatoprost,1,Overall,600.5,10,647.2,12\n"
           "Latanoprost,Latanoprost,5,Overall,130,1000,129,1100\n"
           "Latanoprost,Latanoprost,1,Sandoz,90,500,80,400\n"
           "Mirvaso,Brimonidine Tartrate,1,Overall,3,1,4,1\n"
           "Dorzolamide-Timolol,Dorzolamide HCl/Timolol Maleat,10,Overall,55,29,56,30\n"
           "Eliquis,Apixaban,1,Overall,9999,9,9999,9\n")
    l = {x["marque"]: x for x in cm.medicare_lignes(csv)}
    assert set(l) == {"Lumigan", "Latanoprost", "Dorzolamide-Timolol"}
    assert l["Lumigan"]["type"] == "marque" and l["Latanoprost"]["type"] == "generique"
    assert l["Dorzolamide-Timolol"]["type"] == "generique"
    assert l["Lumigan"]["depenses"] == {"2023": 600, "2024": 647} and l["Latanoprost"]["prescriptions"]["2024"] == 1100
