"""Fourchette d'incertitude de la projection 2030, par province, selon son palier de stabilite.

Principe : le test a origine glissante (modele_predictif.py) mesure l'erreur relative reelle de la prevision demographique,
par palier de stabilite (stable / variable / tres volatile). On prend l'erreur au percentile 80 a l'horizon 3 ans (le plus long
horizon observable) et on l'applique de part et d'autre de l'effectif projete : bas = projete x (1 - e), haut = projete x (1 + e).
Les besoins en salles et en enseignants varient proportionnellement aux effectifs, ils recoivent la meme fourchette relative.

Limites (a dire clairement) : 2030 est a 6 ans de 2024, le test ne depasse pas 3 ans -> la fourchette est un MINIMUM, pas un
intervalle de confiance statistique. Le palier "tres volatile" repose sur peu d'observations (6 a 29 selon l'horizon).

Usage : python fourchette_projection.py <racine_du_projet>
"""
import os
import sys

import numpy as np
import pandas as pd

HORIZON_REF = 3
racine = sys.argv[1]
d4 = os.path.join(racine, "04_analyse")

proj = pd.read_csv(os.path.join(d4, "projection_2030_resume.csv"), sep=";", dtype={"pcode_province_old": str})
inc = pd.read_csv(os.path.join(d4, "modele_incertitude_par_palier.csv"), sep=";")
pal = pd.read_csv(os.path.join(d4, "modele_fiabilite_provinces.csv"), sep=";", dtype={"pcode_province_old": str})

e = inc[inc.horizon == HORIZON_REF].set_index("palier")["erreur_p80"].round(4)      # 4 decimales : meme valeur que la page web
pal["marge_relative"] = pal["palier"].map(e)
out = proj.merge(pal[["pcode_province_old", "palier", "volatilite", "marge_relative"]], on="pcode_province_old", how="left")
assert out["marge_relative"].notna().all(), "province sans palier"

for col, nom in (("eleves_projetes", "eleves"), ("salles_necessaires", "salles_necessaires"),
                 ("enseignants_necessaires", "enseignants_necessaires")):
    out[f"{nom}_bas"] = np.floor(out[col] * (1 - out["marge_relative"]) + 0.5).astype(int)     # arrondi demi-superieur (= Math.round de la page)
    out[f"{nom}_haut"] = np.floor(out[col] * (1 + out["marge_relative"]) + 0.5).astype(int)

# besoins A CONSTRUIRE / A RECRUTER aux bornes : on recalcule a partir des eleves bas / haut (meme regle que la page web : calc.js, bande())
for borne in ("bas", "haut"):
    el = out[f"eleves_{borne}"]
    out[f"salles_a_construire_{borne}"] = (-(-el // out["norme_eleves_salle"].astype(int))).sub(out["nb_salles"]).clip(lower=0).astype(int)
    out[f"enseignants_a_recruter_{borne}"] = (-(-el // out["norme_eleves_enseignant"].astype(int))).sub(out["nb_enseignants"]).clip(lower=0).astype(int)

cols = ["scenario", "annee_scolaire", "pcode_province_old", "province", "palier", "volatilite", "marge_relative",
        "eleves_projetes", "eleves_bas", "eleves_haut", "salles_necessaires", "salles_necessaires_bas", "salles_necessaires_haut",
        "enseignants_necessaires", "enseignants_necessaires_bas", "enseignants_necessaires_haut",
        "salles_a_construire", "salles_a_construire_bas", "salles_a_construire_haut",
        "enseignants_a_recruter", "enseignants_a_recruter_bas", "enseignants_a_recruter_haut"]
out[cols].to_csv(os.path.join(d4, "projection_2030_fourchette.csv"), sep=";", index=False, encoding="utf-8", float_format="%.4f")

print("Marge relative retenue (erreur p80, horizon 3 ans) :", {k: round(float(v), 3) for k, v in e.items()})
tot = out.groupby("scenario")[["eleves_projetes", "eleves_bas", "eleves_haut"]].sum()
tot["ecart_relatif"] = (tot["eleves_haut"] - tot["eleves_bas"]) / 2 / tot["eleves_projetes"]
print("\nTotal national (somme des provinces) :")
print(tot.round(3).to_string())
print("\nNB : les marges des provinces ne s'annulent pas forcement au niveau national ; ce total est la somme brute des bornes.")
