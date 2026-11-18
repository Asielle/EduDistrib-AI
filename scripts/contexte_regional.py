"""Contexte regional annuel (13 regions, 2015-2016 a 2024-2025) tire du classeur DGESS :
taux brut d'acces (TBA), taux brut de scolarisation (TBS), taux d'achevement du primaire, taux de reussite au CEP, effectifs du prescolaire.

Ce sont des variables de REGION (identiques pour toutes les provinces d'une region), a joindre au panel sur (region_ancienne, annee_debut).
Le TBS/TBA officiels reposent sur les denominateurs de la DGESS, differents de ceux du panel (projections INSD) : ne pas les melanger.
Colonnes lues par POSITION (en-tetes parasites dans le classeur) : pour les feuilles 'G/F/T', la colonne T de l'annee k (0 = 2015-2016) est 3 + 3k.
Taux de reussite au CEP : l'annee du tableau est celle de la fin de l'annee scolaire (2016 = annee scolaire 2015-2016).

Sortie : 03_transformation/contexte_region_annee.csv
Usage : python contexte_regional.py <racine_du_projet>
"""
import os
import sys

import pandas as pd

racine = sys.argv[1]
F = os.path.join(racine, "DONNEES_STATISTQUES_ PRESCOLAIRE ET PRIMAIRE_2016_2025_DCB.xlsx")
ALIAS = {"HAUT-BASSINS": "HAUTS-BASSINS", "PLATEAU CENTRAL": "PLATEAU-CENTRAL"}
REGIONS = ["BOUCLE DU MOUHOUN", "CASCADES", "CENTRE", "CENTRE-EST", "CENTRE-NORD", "CENTRE-OUEST", "CENTRE-SUD", "EST", "HAUTS-BASSINS",
           "NORD", "PLATEAU-CENTRAL", "SAHEL", "SUD-OUEST"]


def triplets(feuille, nom):
    """1er tableau de la feuille : 13 regions x 10 annees, colonne T de chaque annee."""
    d = pd.read_excel(F, sheet_name=feuille, header=None)
    out = []
    for i in range(3, 16):
        reg = ALIAS.get(str(d.iat[i, 0]).strip(), str(d.iat[i, 0]).strip())
        for k in range(10):
            out.append({"region": reg, "annee_debut": 2015 + k, nom: pd.to_numeric(d.iat[i, 3 + 3 * k], errors="coerce")})
    return pd.DataFrame(out)


def cep():
    d = pd.read_excel(F, sheet_name="Feuil9", header=None).iloc[2:, :12]
    d[0] = d[0].ffill()
    d = d[d[1].astype(str).str.strip().str.upper() == "TOTAL"]
    out = []
    for _, r in d.iterrows():
        reg = ALIAS.get(str(r[0]).strip(), str(r[0]).strip())
        if reg == "NATIONAL":
            continue
        for k, v in enumerate(r.iloc[2:12]):
            out.append({"region": reg, "annee_debut": 2015 + k, "taux_reussite_cep": pd.to_numeric(v, errors="coerce")})
    return pd.DataFrame(out)


C = triplets("Feuil6", "tba").merge(triplets("Feuil7", "tbs_officiel"), on=["region", "annee_debut"]) \
    .merge(triplets("Feuil8", "taux_achevement"), on=["region", "annee_debut"]).merge(cep(), on=["region", "annee_debut"]) \
    .merge(triplets("PRESCOLAIRE", "eleves_prescolaire"), on=["region", "annee_debut"])
assert sorted(C.region.unique()) == sorted(REGIONS), sorted(C.region.unique())
assert len(C) == 130
C.to_csv(os.path.join(racine, "03_transformation", "contexte_region_annee.csv"), sep=";", index=False, encoding="utf-8", float_format="%.3f")
print(len(C), "lignes (13 regions x 10 annees) ;", C.isna().sum().to_dict())
pd.set_option("display.width", 200)
print("\nTBS officiel par region (%)")
print(C.pivot(index="region", columns="annee_debut", values="tbs_officiel").round(0).astype("Int64").to_string())
print("\nTaux de reussite au CEP (%)")
print(C.pivot(index="region", columns="annee_debut", values="taux_reussite_cep").round(0).astype("Int64").to_string())
