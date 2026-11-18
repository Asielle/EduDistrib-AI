"""Controle du panel par les totaux REGIONAUX officiels (classeur DGESS 2015-2016 a 2024-2025) et extraction des series regionales.

Le classeur DONNEES_STATISTQUES_ PRESCOLAIRE ET PRIMAIRE_2016_2025_DCB.xlsx donne, par region et par annee, les effectifs, le nombre d'ecoles
et les nouveaux inscrits au CP1. On compare la somme des provinces du panel (par region_ancienne) a ces totaux : un ecart important signale une
province dont les ecoles n'ont pas rapporte (ou un probleme d'extraction).
Colonnes lues par POSITION (la 1re ligne d'en-tete du classeur contient du texte parasite) : colonnes 2..11 = annees scolaires 2015-2016..2024-2025.

Sorties : 03_transformation/series_regionales_dgess.csv (region, annee_debut, eleves, ecoles, nouveaux_cp1)
          04_analyse/controle_panel_vs_regions.csv (region, annee_debut, panel, officiel, ecart_relatif, grandeur)
Usage : python controle_regions.py <racine_du_projet>
"""
import os
import sys

import pandas as pd

racine = sys.argv[1]
P = lambda *x: os.path.join(racine, *x)
F = P("DONNEES_STATISTQUES_ PRESCOLAIRE ET PRIMAIRE_2016_2025_DCB.xlsx")
ANNEES = list(range(2015, 2025))
ALIAS = {"HAUT-BASSINS": "HAUTS-BASSINS", "PLATEAU CENTRAL": "PLATEAU-CENTRAL"}


def lire(feuille, col_ligne):
    """col_ligne : valeur de la 2e colonne qui designe la ligne total ('TOTAL' ou 'Total')."""
    d = pd.read_excel(F, sheet_name=feuille, header=None).iloc[2:, :12]
    d[0] = d[0].ffill()
    d = d[d[1].astype(str).str.strip().str.upper() == col_ligne.upper()]
    d = d[d[0] != "NATIONAL"]
    out = []
    for _, r in d.iterrows():
        reg = ALIAS.get(str(r[0]).strip(), str(r[0]).strip())
        for a, v in zip(ANNEES, r.iloc[2:12]):
            out.append({"region": reg, "annee_debut": a, "valeur": pd.to_numeric(v, errors="coerce")})
    return pd.DataFrame(out)


S = (lire("Feuil1", "TOTAL").rename(columns={"valeur": "eleves"})
     .merge(lire("Feuil13", "Total").rename(columns={"valeur": "ecoles"}), on=["region", "annee_debut"], how="outer")
     .merge(lire("Feuil5", "TOTAL").rename(columns={"valeur": "nouveaux_cp1"}), on=["region", "annee_debut"], how="outer"))
assert S.region.nunique() == 13, S.region.unique()
S.to_csv(P("03_transformation", "series_regionales_dgess.csv"), sep=";", index=False, encoding="utf-8")

pan = pd.read_csv(P("03_transformation", "panel_province_annee.csv"), sep=";")
g = pan.groupby(["region_ancienne", "annee_debut"]).agg(eleves=("nb_eleves", "sum"), ecoles=("nb_ecoles", "sum")).reset_index().rename(columns={"region_ancienne": "region"})
rows = []
for grandeur in ("eleves", "ecoles"):
    m = g.merge(S[["region", "annee_debut", grandeur]], on=["region", "annee_debut"], suffixes=("_panel", "_officiel"))
    for r in m.itertuples():
        a, b = getattr(r, f"{grandeur}_panel"), getattr(r, f"{grandeur}_officiel")
        rows.append({"region": r.region, "annee_debut": r.annee_debut, "grandeur": grandeur, "panel": a, "officiel": b,
                     "ecart_relatif": (a - b) / b if b else float("nan")})
C = pd.DataFrame(rows)
C.to_csv(P("04_analyse", "controle_panel_vs_regions.csv"), sep=";", index=False, encoding="utf-8", float_format="%.4f")

pd.set_option("display.width", 220)
for grandeur in ("eleves", "ecoles"):
    t = C[C.grandeur == grandeur].pivot(index="region", columns="annee_debut", values="ecart_relatif")
    print(f"\nECART RELATIF panel vs officiel - {grandeur} (0 = identique)")
    print((t * 100).round(1).to_string())
n = C[(C.grandeur == "eleves") & (C.ecart_relatif.abs() > 0.02)]
print(f"\n{len(n)} couples region-annee avec un ecart > 2 % sur les effectifs (sur {int((C.grandeur == 'eleves').sum())}).")
