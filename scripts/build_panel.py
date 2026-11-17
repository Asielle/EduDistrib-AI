"""Construction du panel province x annee scolaire (45 anciennes provinces x 8 annees, 2017-2018 a 2024-2025).

Joint les trois jeux nettoyes :
  tableau_I1_propre.csv       ecoles, salles de classe, groupes pedagogiques, maitres, eleves
  enseignants_IV1_propre.csv  enseignants (tous), par statut et sexe
  salles_etat_propre.csv      murs, toitures, anciennete des salles, logements de maitre
  equipement_ecoles_propre.csv  ecoles avec eau potable, electricite, latrines, cantine, cloture (tableau V.4)
(plus eleves par milieu, population INSD, deplaces CONASUR) et calcule les indicateurs de repartition (ratios, parts, ecarts a une norme).

Les normes sont des HYPOTHESES DE TRAVAIL (parametres ci-dessous) a confirmer avec le ministere.

Usage :
    python build_panel.py <dossier_02_nettoyage> <dossier_03_transformation> [norme_eleves_salle] [norme_eleves_enseignant]
"""
import os
import sys

import numpy as np
import pandas as pd

NORME_ELEVES_SALLE = 50.0        # standard de 50 eleves par salle au primaire (JICA 2009, rapport du 4e projet d'ecoles primaires, p. 40) ; 40 et 45 en variantes
NORME_ELEVES_ENSEIGNANT = 40.0   # hypothese : 40 eleves par enseignant

DICTIONNAIRE = [
    # (variable, type, description)
    ("annee_scolaire", "texte", "Annee scolaire, ex. 2024-2025 (differente de l'annee civile)"),
    ("annee_debut", "entier", "Annee civile de debut de l'annee scolaire (2024 pour 2024-2025)"),
    ("pcode_province_old", "texte", "P-code de l'ANCIENNE province (COD-AB, colonne adm2_pcode_old) : cle de jointure"),
    ("province", "texte", "Nom de l'ancienne province (45 provinces)"),
    ("region_ancienne", "texte", "Ancienne region (13) telle que dans les annuaires DGESS"),
    ("pcode_region_nouvelle", "texte", "P-code de la region dans le nouveau decoupage (17 regions)"),
    ("region_nouvelle", "texte", "Region nouvelle (COD-AB 2025)"),
    ("pcodes_province_new", "texte", "P-code(s) des provinces nouvelles correspondantes (plusieurs si scindee, separes par |)"),
    ("scindee", "booleen", "Vrai si l'ancienne province a ete scindee en deux provinces nouvelles (Soum, Tapoa)"),
    ("donnee_absente", "booleen", "Vrai si la province n'apparait pas dans les annuaires cette annee-la (Komandjari 2022-2023 : ecoles fermees)"),
    ("nb_ecoles", "entier", "Nombre d'ecoles primaires (public + prive)"),
    ("nb_salles", "entier", "Nombre de salles de classe (public + prive)"),
    ("nb_groupes", "entier", "Nombre de groupes pedagogiques (public + prive)"),
    ("nb_maitres", "entier", "Maitres charges de cours (tableau I.1) : plus restreint que nb_enseignants"),
    ("nb_eleves", "entier", "Effectif d'eleves (public + prive)"),
    ("nb_ecoles_public", "entier", "Ecoles publiques"),
    ("nb_ecoles_prive", "entier", "Ecoles privees"),
    ("nb_salles_public", "entier", "Salles de classe des ecoles publiques"),
    ("nb_salles_prive", "entier", "Salles de classe des ecoles privees"),
    ("nb_eleves_public", "entier", "Eleves du public"),
    ("nb_eleves_prive", "entier", "Eleves du prive"),
    ("nb_enseignants", "entier", "Tous les enseignants (tableau IV.1), public + prive"),
    ("nb_enseignants_public", "entier", "Enseignants du public"),
    ("nb_enseignants_prive", "entier", "Enseignants du prive"),
    ("nb_enseignantes", "entier", "Enseignantes (femmes), public + prive"),
    ("nb_enseignants_tenant_classe", "entier", "Enseignants qui tiennent une classe"),
    ("salles_en_dur", "entier", "Salles de classe aux murs en dur"),
    ("salles_semi_dur", "entier", "Salles aux murs en semi-dur"),
    ("salles_paille_banco", "entier", "Salles aux murs en paille, banco ou autre materiau precaire"),
    ("salles_murs_mauvais_etat", "entier", "Salles dont les murs sont en mauvais etat"),
    ("salles_toit_mauvais_etat", "entier", "Salles dont la toiture est en mauvais etat"),
    ("salles_avant_1995", "entier", "Salles mises en service avant 1995 (plus de 30 ans)"),
    ("salles_apres_2015", "entier", "Salles mises en service apres 2015"),
    ("nb_ecoles_sans_logement", "entier", "Ecoles sans logement de maitre"),
    ("nb_logements_maitre", "entier", "Logements de maitre (total)"),
    ("nb_logements_bon_etat", "entier", "Logements de maitre en bon etat ou acceptable"),
    ("pop_totale", "entier", "Population totale de la province (projection INSD, annee civile = annee_debut ; vide avant 2020)"),
    ("pop_6_11", "entier", "Population de 6 a 11 ans (projection INSD ; vide avant 2020)"),
    ("tbs", "reel", "Taux brut de scolarisation = eleves / pop_6_11 (peut depasser 1 : eleves hors age, eleves venus d'ailleurs)"),
    ("date_reference_pdi", "texte", "Date du releve CONASUR retenu (le plus proche du 31 octobre de l'annee de rentree, +/- 60 jours)"),
    ("pdi_hebergees", "entier", "Personnes deplacees internes HEBERGEES dans la province a cette date (destination, pas origine) ; vide si aucun releve (2023-2024, 2024-2025)"),
    ("pdi_par_100_hab", "reel", "pdi_hebergees pour 100 habitants (pop_totale)"),
    ("pdi_dernier_stock_connu", "entier", "PDI hebergees au dernier releve disponible (31 mars 2023), repetees sur toutes les annees : contexte pour 2023-2025"),
    ("pdi_dernier_stock_par_100_hab", "reel", "pdi_dernier_stock_connu pour 100 habitants"),
    ("eleves_par_salle", "reel", "Eleves / salles de classe"),
    ("eleves_par_enseignant", "reel", "Eleves / enseignants (tous)"),
    ("eleves_par_maitre", "reel", "Eleves / maitres charges de cours"),
    ("eleves_par_groupe", "reel", "Eleves / groupes pedagogiques"),
    ("eleves_par_ecole", "reel", "Eleves / ecoles"),
    ("salles_par_ecole", "reel", "Salles / ecoles"),
    ("part_eleves_prive", "reel", "Part des eleves scolarises dans le prive (0-1)"),
    ("superficie_km2", "reel", "Superficie de l'ancienne province en km2 (COD-AB ; somme des deux parties pour Soum et Tapoa)"),
    ("km2_par_ecole", "reel", "Superficie / nombre d'ecoles primaires en activite : territoire moyen desservi par une ecole"),
    ("distance_theorique_ecole_km", "reel", "0,5 x racine(km2_par_ecole) : distance moyenne THEORIQUE a l'ecole la plus proche si les ecoles etaient reparties regulierement ; ordre de grandeur, pas la distance reelle des villages"),
    ("enfants_6_11_par_ecole", "reel", "Enfants de 6 a 11 ans / ecoles primaires (vide avant 2020)"),
    ("part_salles_precaires", "reel", "Salles aux murs en paille/banco/autre / salles (0-1)"),
    ("part_salles_murs_mauvais_etat", "reel", "Salles aux murs en mauvais etat / salles (0-1)"),
    ("part_salles_anciennes", "reel", "Salles de plus de 30 ans (avant 1995) / salles (0-1)"),
    ("part_ecoles_sans_logement", "reel", "Ecoles sans logement de maitre / ecoles (0-1)"),
    ("part_enseignantes", "reel", "Enseignantes / enseignants (0-1)"),
    ("eleves_urbain", "entier", "Eleves scolarises en milieu urbain (public + prive, tableau I.2)"),
    ("eleves_rural", "entier", "Eleves scolarises en milieu rural"),
    ("filles_urbain", "entier", "Filles scolarisees en milieu urbain"),
    ("filles_rural", "entier", "Filles scolarisees en milieu rural"),
    ("nb_enseignants_urbain", "entier", "Enseignants en milieu urbain (tableau IV.1.4)"),
    ("nb_enseignants_rural", "entier", "Enseignants en milieu rural (tableau IV.1.5)"),
    ("part_eleves_rurale", "reel", "Part des eleves scolarises en milieu rural (0-1)"),
    ("part_filles_urbain", "reel", "Filles / eleves en milieu urbain (0-1) : 0,5 = parite"),
    ("part_filles_rural", "reel", "Filles / eleves en milieu rural (0-1)"),
    ("eleves_par_enseignant_urbain", "reel", "Eleves / enseignants en milieu urbain"),
    ("eleves_par_enseignant_rural", "reel", "Eleves / enseignants en milieu rural"),
    ("rapport_rural_urbain_eleves_par_ens", "reel", "eleves_par_enseignant_rural / eleves_par_enseignant_urbain : plus de 1 = le rural est moins bien dote"),
    ("enseignants_a_deplacer_urbain_vers_rural", "entier", "Enseignants a deplacer du milieu urbain vers le rural pour egaliser les eleves par enseignant DANS la province (negatif : vers l'urbain). Indicateur, pas une recommandation : les conditions de vie en zone rurale ne sont pas modelisees"),
    ("ecoles_eau_potable", "entier", "Ecoles disposant d'eau potable (tableau V.4 / VI.4 des annuaires, public + prive)"),
    ("ecoles_electricite", "entier", "Ecoles disposant d'electricite"),
    ("ecoles_latrines", "entier", "Ecoles disposant de latrines"),
    ("ecoles_cantines", "entier", "Ecoles disposant d'une cantine scolaire"),
    ("ecoles_cloture", "entier", "Ecoles disposant d'une cloture"),
    ("part_ecoles_eau_potable", "reel", "Ecoles avec eau potable / ecoles fonctionnelles du tableau V.4 (0-1)"),
    ("part_ecoles_electricite", "reel", "Ecoles avec electricite / ecoles fonctionnelles (0-1)"),
    ("part_ecoles_latrines", "reel", "Ecoles avec latrines / ecoles fonctionnelles (0-1)"),
    ("part_ecoles_cantines", "reel", "Ecoles avec cantine / ecoles fonctionnelles (0-1)"),
    ("part_ecoles_cloture", "reel", "Ecoles avec cloture / ecoles fonctionnelles (0-1)"),
    ("norme_eleves_salle", "reel", "Norme d'eleves par salle utilisee pour les besoins : 50, standard cite pour le primaire par la JICA (2009) ; peut avoir evolue"),
    ("norme_eleves_enseignant", "reel", "HYPOTHESE de travail : 40 eleves par enseignant (aucune norme trouvee)"),
    ("salles_necessaires", "entier", "ceil(eleves / norme_eleves_salle)"),
    ("enseignants_necessaires", "entier", "ceil(eleves / norme_eleves_enseignant)"),
    ("ecart_salles", "entier", "salles_necessaires - nb_salles (positif = deficit, negatif = excedent)"),
    ("ecart_enseignants", "entier", "enseignants_necessaires - nb_enseignants (positif = deficit, negatif = excedent)"),
    ("deficit_salles", "entier", "max(0, ecart_salles)"),
    ("deficit_enseignants", "entier", "max(0, ecart_enseignants)"),
]


def lire(dossier, nom):
    return pd.read_csv(os.path.join(dossier, nom), sep=";", encoding="utf-8", dtype=str).replace({"": np.nan})


def num(df, cols):
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def a_plat(df, cle, valeurs, prefixe_statut):
    """Un tableau long (statut en lignes) -> colonnes par statut."""
    out = []
    for st, suf in prefixe_statut.items():
        sub = df[df["statut"] == st][cle + valeurs].copy()
        sub = sub.rename(columns={v: v + suf for v in valeurs})
        out.append(sub.set_index(cle))
    return pd.concat(out, axis=1)


def main():
    d_in, d_out = sys.argv[1], sys.argv[2]
    ns = float(sys.argv[3]) if len(sys.argv) > 3 else NORME_ELEVES_SALLE
    ne = float(sys.argv[4]) if len(sys.argv) > 4 else NORME_ELEVES_ENSEIGNANT
    os.makedirs(d_out, exist_ok=True)

    ref = lire(d_in, "ref_provinces.csv")
    i1 = num(lire(d_in, "tableau_I1_propre.csv"),
             ["nb_ecoles", "nb_salles", "nb_groupes", "nb_maitres", "nb_eleves"])
    en = num(lire(d_in, "enseignants_IV1_propre.csv"), ["nb_enseignants", "tenant_classe"])
    sa = lire(d_in, "salles_etat_propre.csv")
    sa_cols = [c for c in sa.columns if c.split("_")[0] in ("annee", "log", "surf", "murs", "toit")
               and c != "annee_scolaire"]
    sa = num(sa, sa_cols)

    cle = ["annee_scolaire", "pcode_province_old"]
    st = {"Total": "", "Public": "_public", "Prive": "_prive"}

    p = i1[i1["niveau"] == "province"]
    a = a_plat(p, cle, ["nb_ecoles", "nb_salles", "nb_groupes", "nb_maitres", "nb_eleves"], st)

    e = en[(en["niveau"] == "province") & (en["sexe"] == "T")]
    b = a_plat(e, cle, ["nb_enseignants"], st)
    f = en[(en["niveau"] == "province") & (en["sexe"] == "F") & (en["statut"] == "Total")]
    b["nb_enseignantes"] = f.set_index(cle)["nb_enseignants"]
    b["nb_enseignants_tenant_classe"] = e[e["statut"] == "Total"].set_index(cle)["tenant_classe"]

    s = sa[(sa["niveau"] == "province") & (sa["statut"] == "Total")].set_index(cle)
    c = pd.DataFrame(index=s.index)
    c["salles_en_dur"] = s["murs_en_dur"]
    c["salles_semi_dur"] = s["murs_semi_dur"]
    c["salles_paille_banco"] = s["murs_paille_banco_autre"]
    c["salles_murs_mauvais_etat"] = s["murs_etat_mauvais"]
    c["salles_toit_mauvais_etat"] = s["toit_etat_mauvais"]
    c["salles_avant_1995"] = s[["annee_avant_1965", "annee_de_1965_1975", "annee_de_1975_1985",
                                "annee_de_1985_1995"]].sum(axis=1, min_count=4)
    c["salles_apres_2015"] = s["annee_apres_2015"]
    c["nb_ecoles_sans_logement"] = s["log_ecoles_sans_logement"]
    c["nb_logements_maitre"] = s["log_logements"]
    c["nb_logements_bon_etat"] = s["log_logements_bon_etat"]
    c["_salles_annee_total"] = s["annee_total"]
    c["_salles_murs_total"] = s["murs_total"]

    # squelette complet : 45 provinces x 8 annees
    annees = sorted(i1["annee_scolaire"].unique())
    base = pd.MultiIndex.from_product([annees, ref["pcode_province_old"]], names=cle).to_frame(index=False)
    ref = ref.rename(columns={"pcode_province_old": "pcode_province_old", "region_ancienne_dgess": "region_ancienne"})
    base = base.merge(ref, on="pcode_province_old", how="left")
    # milieu urbain / rural : eleves (tableau I.2) et enseignants (tableaux IV.1.4 et IV.1.5)
    f_mil = os.path.join(d_in, "eleves_milieu_propre.csv")
    dm = pd.DataFrame(index=a.index)
    if os.path.exists(f_mil):
        mil = pd.read_csv(f_mil, sep=";", dtype={"pcode_province_old": str})
        mil = mil[mil.niveau == "province"].set_index(cle)
        dm["eleves_urbain"], dm["eleves_rural"] = mil["urbain_total"], mil["rural_total"]
        dm["filles_urbain"], dm["filles_rural"] = mil["urbain_filles"], mil["rural_filles"]
        eu = en[(en["niveau"] == "province") & (en["sexe"] == "T") & en["statut"].isin(["Urbain", "Rural"])]
        for stt, col in (("Urbain", "nb_enseignants_urbain"), ("Rural", "nb_enseignants_rural")):
            dm[col] = eu[eu["statut"] == stt].set_index(cle)["nb_enseignants"]
    # equipement des ecoles (eau, electricite, latrines...) : tableau V.4 / VI.4, public + prive
    f_eq = os.path.join(d_in, "equipement_ecoles_propre.csv")
    de = pd.DataFrame(index=a.index)
    if os.path.exists(f_eq):
        eq = pd.read_csv(f_eq, sep=";", dtype={"pcode_province_old": str})
        eq = eq[(eq.niveau == "province") & (eq.statut == "Total")].set_index(cle)
        for col in ("eau_potable", "electricite", "latrines", "cantines", "cloture"):
            de["ecoles_" + col] = eq["equip_" + col]
            de["part_ecoles_" + col] = (eq["equip_" + col] / eq["equip_ecoles"]).where(eq["equip_ecoles"] > 0)
    panel = base.set_index(cle).join([a, b, c, dm, de], how="left").reset_index()

    panel["annee_debut"] = panel["annee_scolaire"].str[:4].astype(int)
    panel["scindee"] = panel["scindee"].eq("oui")
    panel["donnee_absente"] = panel["nb_eleves"].isna()

    # ---- population INSD (2020-2035) : denominateur du taux de scolarisation ----
    f_pop = os.path.join(d_in, "population_province_age.csv")
    panel["pop_totale"] = np.nan
    panel["pop_6_11"] = np.nan
    if os.path.exists(f_pop):
        pp = pd.read_csv(f_pop, sep=";", dtype={"pcode_province_old": str})
        pp = pp[pp.sexe == "E"]
        for col, g in (("pop_totale", "total"), ("pop_6_11", "6-11")):
            m = pp[pp.groupe_age == g].set_index(["pcode_province_old", "annee"])["population"]
            panel[col] = [m.get((p, a), np.nan) for p, a in zip(panel["pcode_province_old"], panel["annee_debut"])]
    panel["tbs"] = (panel["nb_eleves"] / panel["pop_6_11"]).where(panel["pop_6_11"] > 0)

    # ---- personnes deplacees internes hebergees (CONASUR) ----
    # releve le plus proche du 31 octobre de l'annee de rentree (a +/- 60 jours) ; 2023-2024 et 2024-2025 : pas de releve
    f_pdi = os.path.join(d_in, "pdi_province_date.csv")
    panel["date_reference_pdi"] = pd.NA
    panel["pdi_hebergees"] = np.nan
    panel["pdi_dernier_stock_connu"] = np.nan
    if os.path.exists(f_pdi):
        pdi = pd.read_csv(f_pdi, sep=";", dtype={"pcode_province_old": str}, parse_dates=["date"])
        dates = sorted(pdi["date"].unique())
        derniere = pdi["date"].max()
        dernier = pdi[pdi["date"] == derniere].set_index("pcode_province_old")["pdi_total"]
        panel["pdi_dernier_stock_connu"] = panel["pcode_province_old"].map(dernier).fillna(0)
        for an in sorted(panel["annee_debut"].unique()):
            cible = pd.Timestamp(f"{an}-10-31")
            proche = min(dates, key=lambda x: abs(x - cible))
            if abs((proche - cible).days) > 60:
                continue
            masque = panel["annee_debut"] == an
            snap = pdi[pdi["date"] == proche].set_index("pcode_province_old")["pdi_total"]
            panel.loc[masque, "pdi_hebergees"] = panel.loc[masque, "pcode_province_old"].map(snap).fillna(0)
            panel.loc[masque, "date_reference_pdi"] = proche.strftime("%Y-%m-%d")
        panel["pdi_hebergees"] = panel["pdi_hebergees"].astype(float)
    panel["pdi_par_100_hab"] = (100 * panel["pdi_hebergees"] / panel["pop_totale"]).where(panel["pop_totale"] > 0)
    panel["pdi_dernier_stock_par_100_hab"] = (100 * panel["pdi_dernier_stock_connu"] / panel["pop_totale"]).where(panel["pop_totale"] > 0)

    def ratio(n, d):
        return (panel[n] / panel[d]).where(panel[d] > 0)

    panel["eleves_par_salle"] = ratio("nb_eleves", "nb_salles")
    panel["eleves_par_enseignant"] = ratio("nb_eleves", "nb_enseignants")
    panel["eleves_par_maitre"] = ratio("nb_eleves", "nb_maitres")
    panel["eleves_par_groupe"] = ratio("nb_eleves", "nb_groupes")
    panel["eleves_par_ecole"] = ratio("nb_eleves", "nb_ecoles")
    panel["salles_par_ecole"] = ratio("nb_salles", "nb_ecoles")
    panel["part_eleves_prive"] = ratio("nb_eleves_prive", "nb_eleves")
    # acces : distance moyenne theorique a l'ecole la plus proche, si les ecoles en activite etaient reparties regulierement sur la
    # province : 0,5 * racine(superficie / nombre d'ecoles). C'est un ordre de grandeur (pas la vraie distance des villages).
    panel["superficie_km2"] = pd.to_numeric(panel["superficie_km2"], errors="coerce")
    panel["km2_par_ecole"] = (panel["superficie_km2"] / panel["nb_ecoles"]).where(panel["nb_ecoles"] > 0)
    panel["distance_theorique_ecole_km"] = 0.5 * np.sqrt(panel["km2_par_ecole"])
    panel["enfants_6_11_par_ecole"] = (panel["pop_6_11"] / panel["nb_ecoles"]).where(panel["nb_ecoles"] > 0)
    panel["part_salles_precaires"] = (panel["salles_paille_banco"] / panel["_salles_murs_total"]).where(panel["_salles_murs_total"] > 0)
    panel["part_salles_murs_mauvais_etat"] = (panel["salles_murs_mauvais_etat"] / panel["_salles_murs_total"]).where(panel["_salles_murs_total"] > 0)
    panel["part_salles_anciennes"] = (panel["salles_avant_1995"] / panel["_salles_annee_total"]).where(panel["_salles_annee_total"] > 0)
    panel["part_ecoles_sans_logement"] = ratio("nb_ecoles_sans_logement", "nb_ecoles")
    panel["part_enseignantes"] = ratio("nb_enseignantes", "nb_enseignants")
    if "eleves_urbain" in panel:
        panel["part_eleves_rurale"] = ratio("eleves_rural", "nb_eleves")
        panel["part_filles_urbain"] = ratio("filles_urbain", "eleves_urbain")
        panel["part_filles_rural"] = ratio("filles_rural", "eleves_rural")
        panel["eleves_par_enseignant_urbain"] = ratio("eleves_urbain", "nb_enseignants_urbain")
        panel["eleves_par_enseignant_rural"] = ratio("eleves_rural", "nb_enseignants_rural")
        panel["rapport_rural_urbain_eleves_par_ens"] = panel["eleves_par_enseignant_rural"] / panel["eleves_par_enseignant_urbain"]
        eu_, er_, tu_, tr_ = panel["eleves_urbain"], panel["eleves_rural"], panel["nb_enseignants_urbain"], panel["nb_enseignants_rural"]
        panel["enseignants_a_deplacer_urbain_vers_rural"] = (((er_ * tu_ - eu_ * tr_) / (eu_ + er_)).round()).where((tu_ > 0) & (tr_ > 0) & (eu_ + er_ > 0))

    panel["norme_eleves_salle"] = ns
    panel["norme_eleves_enseignant"] = ne
    panel["salles_necessaires"] = np.ceil(panel["nb_eleves"] / ns)
    panel["enseignants_necessaires"] = np.ceil(panel["nb_eleves"] / ne)
    panel["ecart_salles"] = panel["salles_necessaires"] - panel["nb_salles"]
    panel["ecart_enseignants"] = panel["enseignants_necessaires"] - panel["nb_enseignants"]
    panel["deficit_salles"] = panel["ecart_salles"].clip(lower=0)
    panel["deficit_enseignants"] = panel["ecart_enseignants"].clip(lower=0)

    colonnes = [v for v, _, _ in DICTIONNAIRE]
    manquantes = [x for x in colonnes if x not in panel.columns]
    assert not manquantes, f"colonnes documentees mais absentes : {manquantes}"
    panel = panel[colonnes].sort_values(["annee_scolaire", "pcode_province_old"]).reset_index(drop=True)
    types = {v: t for v, t, _ in DICTIONNAIRE}
    for col, t in types.items():
        if t == "entier" and col != "annee_debut":
            panel[col] = panel[col].astype("Int64")
    panel.to_csv(os.path.join(d_out, "panel_province_annee.csv"), sep=";", index=False, encoding="utf-8",
                 float_format="%.4f")
    pd.DataFrame(DICTIONNAIRE, columns=["variable", "type", "description"]).to_csv(
        os.path.join(d_out, "dictionnaire_variables.csv"), sep=";", index=False, encoding="utf-8")

    # ---- verifications ----
    print(f"panel : {len(panel)} lignes x {len(panel.columns)} colonnes "
          f"({panel['pcode_province_old'].nunique()} provinces x {panel['annee_scolaire'].nunique()} annees)")
    absentes = panel.loc[panel["donnee_absente"], ["annee_scolaire", "province"]].values.tolist()
    print(f"lignes sans donnees : {len(absentes)} -> {absentes}")
    nat = i1[(i1["niveau"] == "national") & (i1["statut"] == "Total")].set_index("annee_scolaire")
    somme = panel.groupby("annee_scolaire")[["nb_eleves", "nb_salles", "nb_ecoles"]].sum()
    for col in ("nb_eleves", "nb_salles", "nb_ecoles"):
        ecart = (somme[col].astype(float) - nat[col]).abs()
        print(f"  somme des provinces vs total national ({col}) : ecart max = {int(ecart.max())}")
    vides = panel.loc[~panel["donnee_absente"]].isna().sum()
    vides = vides[vides > 0]
    print("valeurs vides hors lignes absentes :", dict(vides) if len(vides) else "aucune")
    suivi = panel.groupby("annee_scolaire").agg(
        pop_6_11=("pop_6_11", "sum"), eleves=("nb_eleves", "sum"),
        pdi=("pdi_hebergees", lambda s: s.sum(min_count=1)), date_pdi=("date_reference_pdi", "first"))
    suivi["tbs_national"] = suivi["eleves"] / suivi["pop_6_11"].where(suivi["pop_6_11"] > 0)
    print("\nTBS national et PDI hebergees par annee :")
    print(suivi[["tbs_national", "pdi", "date_pdi"]].to_string())
    print(f"\nnormes de travail : {ns:.0f} eleves/salle, {ne:.0f} eleves/enseignant")
    print(panel.groupby("annee_scolaire")[["deficit_salles", "deficit_enseignants"]].sum().to_string())


if __name__ == "__main__":
    main()
