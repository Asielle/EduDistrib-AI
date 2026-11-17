"""Indice de tension scolaire par ancienne province (45), annee de reference 2024-2025.

Cinq composantes, chacune convertie en rang percentile 0-100 parmi les 45 provinces (100 = situation la plus tendue).
Le rang percentile est robuste aux valeurs extremes (ex. Loroum : 143 eleves/salle en 2022-2023) et se lit sans
formule : "cette province est dans les 10 % les plus tendues pour ce critere".

  salles        eleves par salle de classe                         (plus c'est eleve, plus c'est tendu)
  enseignants   eleves par enseignant
  acces         enfants de 6-11 ans non scolarises = max(0, 1 - TBS)   (capte les ecoles fermees)
  bati          moyenne de la part de salles en materiau precaire (paille/banco) et de la part de salles
                aux murs en mauvais etat
  deplaces      personnes deplacees hebergees pour 100 habitants (releve CONASUR du 31/03/2023)

Ponderation PROPOSEE (a discuter) :
  salles 25 %, enseignants 20 %, acces 25 %, bati 15 %, deplaces 15 %
  = 45 % pour la repartition des salles et des enseignants (coeur du defi 3), 25 % pour l'acces (enfants hors de
    l'ecole), 30 % pour la qualite du bati et la pression des deplaces.

Test de robustesse : plusieurs ponderations alternatives sont comparees (correlation de rang, recouvrement du top 10).

L'indice RELATIF dit ou la tension est la plus forte ; il ne dit pas combien de salles construire. Les volumes viennent
de la projection 2030 (colonnes besoin_*).

Usage :
    python indice_tension.py <panel.csv> <projection_2030_resume.csv> <dossier_sortie>
"""
import os
import sys

import numpy as np
import pandas as pd

ANNEE = "2024-2025"
POIDS = {"salles": 0.25, "enseignants": 0.20, "acces": 0.25, "bati": 0.15, "deplaces": 0.15}
VARIANTES = {
    "proposee": POIDS,
    "poids_egaux": {k: 0.20 for k in POIDS},
    "sans_deplaces": {"salles": 0.30, "enseignants": 0.25, "acces": 0.30, "bati": 0.15, "deplaces": 0.0},
    "ressources_seules": {"salles": 0.50, "enseignants": 0.50, "acces": 0.0, "bati": 0.0, "deplaces": 0.0},
    "acces_et_deplaces": {"salles": 0.10, "enseignants": 0.10, "acces": 0.40, "bati": 0.10, "deplaces": 0.30},
    # le critere "bati" est remplace par "bati + equipement" (moyenne du bati degrade et des ecoles sans eau potable ni latrines)
    "bati_et_equipement": {"salles": 0.25, "enseignants": 0.20, "acces": 0.25, "bati_equip": 0.15, "deplaces": 0.15},
}
assert all(abs(sum(v.values()) - 1) < 1e-9 for v in VARIANTES.values())


def rang_percentile(s):
    """0 = situation la moins tendue, 100 = la plus tendue (45 provinces)."""
    return 100 * (s.rank(method="average") - 1) / (len(s) - 1)


def main():
    panel_csv, proj_csv, d_out = sys.argv[1:4]
    os.makedirs(d_out, exist_ok=True)
    p = pd.read_csv(panel_csv, sep=";", dtype={"pcode_province_old": str})
    p = p[p.annee_scolaire == ANNEE].set_index("pcode_province_old")
    assert len(p) == 45 and not p["donnee_absente"].any()

    ind = pd.DataFrame(index=p.index)
    ind["province"] = p["province"]
    ind["region_ancienne"] = p["region_ancienne"]
    ind["region_nouvelle"] = p["region_nouvelle"]
    ind["pcodes_province_new"] = p["pcodes_province_new"]
    ind["eleves_par_salle"] = p["eleves_par_salle"]
    ind["eleves_par_enseignant"] = p["eleves_par_enseignant"]
    ind["tbs"] = p["tbs"]
    ind["enfants_hors_ecole_part"] = (1 - p["tbs"]).clip(lower=0)
    ind["part_salles_precaires"] = p["part_salles_precaires"]
    ind["part_salles_murs_mauvais_etat"] = p["part_salles_murs_mauvais_etat"]
    ind["bati_degrade"] = (p["part_salles_precaires"] + p["part_salles_murs_mauvais_etat"]) / 2
    ind["pdi_par_100_hab_mars_2023"] = p["pdi_dernier_stock_par_100_hab"]
    ind["pdi_hebergees_mars_2023"] = p["pdi_dernier_stock_connu"]
    manquants = ind.drop(columns=["province", "region_ancienne", "region_nouvelle", "pcodes_province_new"]).isna().sum()
    assert manquants.sum() == 0, f"valeurs manquantes : {manquants[manquants > 0].to_dict()}"

    comp = pd.DataFrame(index=p.index)
    comp["score_salles"] = rang_percentile(ind["eleves_par_salle"])
    comp["score_enseignants"] = rang_percentile(ind["eleves_par_enseignant"])
    comp["score_acces"] = rang_percentile(ind["enfants_hors_ecole_part"])
    comp["score_bati"] = rang_percentile(ind["bati_degrade"])
    comp["score_deplaces"] = rang_percentile(ind["pdi_par_100_hab_mars_2023"])
    # equipement des ecoles (eau potable, latrines) : indicateurs d'information et variante de robustesse (pas dans l'indice propose)
    for col, nom in (("part_ecoles_eau_potable", "eau_potable"), ("part_ecoles_latrines", "latrines"), ("part_ecoles_electricite", "electricite")):
        ind["part_ecoles_" + nom] = p[col]
    assert ind[["part_ecoles_eau_potable", "part_ecoles_latrines"]].notna().all().all()
    manque_equip = ((1 - ind["part_ecoles_eau_potable"]) + (1 - ind["part_ecoles_latrines"])) / 2
    comp_equip = rang_percentile((ind["bati_degrade"] + manque_equip) / 2)

    comp_alt = comp.copy()
    comp_alt["score_bati_equip"] = comp_equip

    def indice(poids):
        return sum(comp_alt[f"score_{k}"] * w for k, w in poids.items())

    res = ind.join(comp)
    res["indice_tension"] = indice(POIDS)
    res["rang"] = res["indice_tension"].rank(ascending=False, method="min").astype(int)
    seuils = res["indice_tension"].quantile([1 / 3, 2 / 3])
    res["niveau"] = np.where(res["indice_tension"] >= seuils.iloc[1], "forte",
                             np.where(res["indice_tension"] >= seuils.iloc[0], "moyenne", "faible"))

    # volumes (projection 2030, scenario de reference) pour ne pas confondre taux et quantites
    pr = pd.read_csv(proj_csv, sep=";", dtype={"pcode_province_old": str})
    for sc, suf in (("statu_quo", "statu_quo"), ("retour_2020_2021", "retour")):
        g = pr[pr.scenario == sc].set_index("pcode_province_old")
        res[f"besoin_salles_2030_{suf}"] = g["salles_a_construire"]
        res[f"besoin_enseignants_2030_{suf}"] = g["enseignants_a_recruter"]
    res["poids_utilises"] = "; ".join(f"{k} {int(w * 100)}%" for k, w in POIDS.items())

    # robustesse
    rob = []
    base_rang = res["indice_tension"].rank(ascending=False)
    top10 = set(res.nsmallest(10, "rang").index)
    for nom, w in VARIANTES.items():
        v = indice(w)
        rob.append({"variante": nom, "poids": "; ".join(f"{k} {int(x * 100)}%" for k, x in w.items() if x > 0),
                    "correlation_rang_avec_proposee": round(base_rang.corr(v.rank(ascending=False), method="pearson"), 3),
                    "provinces_communes_top10": len(top10 & set(v.nlargest(10).index))})
    rob = pd.DataFrame(rob)

    res = res.sort_values("rang")
    cols = ["rang", "niveau", "indice_tension", "province", "region_ancienne", "region_nouvelle", "pcodes_province_new",
            "score_salles", "score_enseignants", "score_acces", "score_bati", "score_deplaces",
            "eleves_par_salle", "eleves_par_enseignant", "tbs", "enfants_hors_ecole_part", "part_salles_precaires",
            "part_salles_murs_mauvais_etat", "part_ecoles_eau_potable", "part_ecoles_latrines", "part_ecoles_electricite",
            "pdi_par_100_hab_mars_2023", "pdi_hebergees_mars_2023",
            "besoin_salles_2030_statu_quo", "besoin_salles_2030_retour", "besoin_enseignants_2030_statu_quo",
            "besoin_enseignants_2030_retour", "poids_utilises"]
    out = res.reset_index()[["pcode_province_old"] + cols]
    out.to_csv(os.path.join(d_out, "indice_tension_provinces_2024_2025.csv"), sep=";", index=False, encoding="utf-8",
               float_format="%.3f")
    rob.to_csv(os.path.join(d_out, "indice_tension_robustesse.csv"), sep=";", index=False, encoding="utf-8")

    pd.set_option("display.width", 200)
    print(f"Indice de tension {ANNEE} - ponderation : {', '.join(f'{k} {int(w*100)} %' for k, w in POIDS.items())}\n")
    aff = out[["rang", "province", "indice_tension", "niveau", "eleves_par_salle", "eleves_par_enseignant",
               "tbs", "part_salles_precaires", "pdi_par_100_hab_mars_2023"]]
    print("Les 12 provinces les plus tendues :")
    print(aff.head(12).round(2).to_string(index=False))
    print("\nLes 5 moins tendues :")
    print(aff.tail(5).round(2).to_string(index=False))
    print("\nRepartition par region ancienne (niveau forte) :")
    print(out[out.niveau == "forte"].groupby("region_ancienne").size().sort_values(ascending=False).to_string())
    print("\nRobustesse du classement :")
    print(rob.to_string(index=False))


if __name__ == "__main__":
    main()
