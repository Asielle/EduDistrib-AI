"""Projection des besoins en salles de classe et en enseignants a l'horizon 2030, par ancienne province.

Methode (transparente, en 4 etapes) :
  1. Population de 6-11 ans par province et par annee : projections INSD (RGPH 2019, vol. 4, scenario de l'INSD).
  2. Taux brut de scolarisation (TBS) = eleves / population 6-11 ans. Valeur de depart : 2024-2025 (annee_debut 2024).
     Le TBS recalcule ainsi retrouve exactement celui publie par la DGESS pour 2024-2025.
  3. Trois scenarios d'evolution du TBS, par interpolation lineaire de 2024 a 2030 :
       statu_quo          : TBS 2024 maintenu          -> effet demographique seul
       retour_2020_2021   : TBS revient a son niveau de 2020-2021 (avant l'effondrement lie a l'insecurite)
       acces_universel    : TBS atteint 100 % (les provinces deja au-dessus gardent leur niveau)
     eleves(t) = TBS(t) x population 6-11 ans (t)
  4. Besoins = eleves / norme. Deficit = besoin - stock 2024-2025 (stock suppose inchange ; pas d'attrition des
     enseignants ; salles precaires comptees a part).

Horizon : "2030" = annee scolaire 2030-2031 (annee_debut 2030), car la population de l'annee civile N est le
denominateur de l'annee scolaire N-(N+1), comme dans les publications de la DGESS.

NORMES : 50 eleves/salle (standard du primaire cite par la JICA en 2009, a confirmer qu'il est toujours en vigueur) et 40 eleves/enseignant (HYPOTHESE de travail, aucune norme trouvee) par defaut.

Usage :
    python projection_2030.py <panel.csv> <population_province_age.csv> <dossier_sortie> [norme_salle] [norme_enseignant]
"""
import os
import sys

import numpy as np
import pandas as pd

ANNEE_BASE, ANNEE_REF_AVANT_CRISE, HORIZON = 2024, 2020, 2030
SCENARIOS = ["statu_quo", "retour_2020_2021", "acces_universel"]
NORMES_SENSIBILITE = [(40, 40), (45, 40), (50, 40), (45, 45), (50, 50)]


def charger(panel_csv, pop_csv):
    pan = pd.read_csv(panel_csv, sep=";", dtype={"pcode_province_old": str})
    pan = pan.drop(columns=["pop_6_11", "pop_totale", "tbs"], errors="ignore")  # recalcules ici depuis la population INSD
    pop = pd.read_csv(pop_csv, sep=";", dtype={"pcode_province_old": str})
    p = pop[(pop.groupe_age == "6-11") & (pop.sexe == "E")][["pcode_province_old", "annee", "population"]]
    p = p.rename(columns={"population": "pop_6_11", "annee": "annee_debut"})
    return pan, p


def tbs_cibles(pan, pop):
    """TBS de depart et cibles 2030 par province et par scenario."""
    m = pan.merge(pop, on=["pcode_province_old", "annee_debut"], how="left")
    m["tbs"] = m["nb_eleves"] / m["pop_6_11"]
    t0 = m[m.annee_debut == ANNEE_BASE].set_index("pcode_province_old")["tbs"]
    tref = m[m.annee_debut == ANNEE_REF_AVANT_CRISE].set_index("pcode_province_old")["tbs"]
    cibles = pd.DataFrame({"tbs_2024": t0, "tbs_2020": tref})
    cibles["statu_quo"] = cibles["tbs_2024"]
    cibles["retour_2020_2021"] = cibles[["tbs_2024", "tbs_2020"]].max(axis=1)
    cibles["acces_universel"] = cibles["tbs_2024"].clip(lower=1.0)
    return cibles


def projeter(pan, pop, cibles, norme_salle, norme_ens):
    base = pan[pan.annee_debut == ANNEE_BASE].set_index("pcode_province_old")
    stock = base[["province", "region_ancienne", "region_nouvelle", "pcodes_province_new", "nb_salles",
                  "nb_enseignants", "nb_eleves", "salles_paille_banco", "salles_murs_mauvais_etat",
                  "pdi_dernier_stock_connu", "pdi_dernier_stock_par_100_hab"]]
    lignes = []
    for sc in SCENARIOS:
        for t in range(ANNEE_BASE, HORIZON + 1):
            part = (t - ANNEE_BASE) / (HORIZON - ANNEE_BASE)
            tbs = cibles["tbs_2024"] + (cibles[sc] - cibles["tbs_2024"]) * part
            popt = pop[pop.annee_debut == t].set_index("pcode_province_old")["pop_6_11"]
            d = stock.copy()
            d["scenario"], d["annee_debut"] = sc, t
            d["annee_scolaire"] = f"{t}-{t + 1}"
            d["pop_6_11"] = popt
            d["tbs"] = tbs
            d["eleves_projetes"] = (tbs * popt).round()
            lignes.append(d.reset_index())
    out = pd.concat(lignes, ignore_index=True)
    out["norme_eleves_salle"], out["norme_eleves_enseignant"] = norme_salle, norme_ens
    out["salles_necessaires"] = np.ceil(out["eleves_projetes"] / norme_salle)
    out["enseignants_necessaires"] = np.ceil(out["eleves_projetes"] / norme_ens)
    out["salles_a_construire"] = (out["salles_necessaires"] - out["nb_salles"]).clip(lower=0)
    out["enseignants_a_recruter"] = (out["enseignants_necessaires"] - out["nb_enseignants"]).clip(lower=0)
    # si les salles precaires (murs paille/banco) sont remplacees, elles sortent du stock
    out["salles_a_construire_avec_remplacement"] = (
        out["salles_necessaires"] - (out["nb_salles"] - out["salles_paille_banco"])).clip(lower=0)
    return out


def main():
    panel_csv, pop_csv, d_out = sys.argv[1:4]
    ns = float(sys.argv[4]) if len(sys.argv) > 4 else 50.0
    ne = float(sys.argv[5]) if len(sys.argv) > 5 else 40.0
    os.makedirs(d_out, exist_ok=True)
    pan, pop = charger(panel_csv, pop_csv)
    cibles = tbs_cibles(pan, pop)
    proj = projeter(pan, pop, cibles, ns, ne)

    cols = ["scenario", "annee_scolaire", "annee_debut", "pcode_province_old", "province", "region_ancienne",
            "region_nouvelle", "pcodes_province_new", "pop_6_11", "tbs", "eleves_projetes",
            "pdi_dernier_stock_connu", "pdi_dernier_stock_par_100_hab",
            "nb_salles", "salles_paille_banco", "nb_enseignants", "norme_eleves_salle",
            "norme_eleves_enseignant", "salles_necessaires", "enseignants_necessaires",
            "salles_a_construire", "salles_a_construire_avec_remplacement", "enseignants_a_recruter"]
    ent = ["pdi_dernier_stock_connu", "nb_salles", "salles_paille_banco", "nb_enseignants", "salles_necessaires", "enseignants_necessaires",
           "salles_a_construire", "salles_a_construire_avec_remplacement", "enseignants_a_recruter",
           "eleves_projetes", "pop_6_11"]
    sortie = proj[cols].copy()
    for c in ent:
        sortie[c] = sortie[c].round().astype("Int64")
    sortie = sortie.sort_values(["scenario", "annee_debut", "pcode_province_old"])
    sortie.to_csv(os.path.join(d_out, "projection_province_annee_scenario.csv"), sep=";", index=False,
                  encoding="utf-8", float_format="%.4f")

    # resume 2030 par province
    r = sortie[sortie.annee_debut == HORIZON].drop(columns=["annee_debut"])
    r.to_csv(os.path.join(d_out, "projection_2030_resume.csv"), sep=";", index=False, encoding="utf-8", float_format="%.4f")

    # sensibilite aux normes (national, 2030)
    rows = []
    for a, b in NORMES_SENSIBILITE:
        p = projeter(pan, pop, cibles, a, b)
        p30 = p[p.annee_debut == HORIZON]
        for sc, g in p30.groupby("scenario"):
            rows.append({"norme_eleves_salle": a, "norme_eleves_enseignant": b, "scenario": sc,
                         "eleves_projetes": int(g.eleves_projetes.sum()),
                         "salles_a_construire": int(g.salles_a_construire.sum()),
                         "salles_a_construire_avec_remplacement": int(g.salles_a_construire_avec_remplacement.sum()),
                         "enseignants_a_recruter": int(g.enseignants_a_recruter.sum())})
    sens = pd.DataFrame(rows)
    sens.to_csv(os.path.join(d_out, "projection_sensibilite_normes.csv"), sep=";", index=False, encoding="utf-8")

    # ---- affichage ----
    base = pan[pan.annee_debut == ANNEE_BASE]
    print(f"Base 2024-2025 : {int(base.nb_eleves.sum()):,} eleves, {int(base.nb_salles.sum()):,} salles, "
          f"{int(base.nb_enseignants.sum()):,} enseignants".replace(",", " "))
    print(f"TBS national 2024-25 : {base.nb_eleves.sum() / pop[pop.annee_debut == ANNEE_BASE].pop_6_11.sum():.1%} ; "
          f"pop 6-11 ans : {int(pop[pop.annee_debut == ANNEE_BASE].pop_6_11.sum()):,} -> "
          f"{int(pop[pop.annee_debut == HORIZON].pop_6_11.sum()):,} en {HORIZON}".replace(",", " "))
    print(f"\nNormes : {ns:.0f} eleves/salle, {ne:.0f} eleves/enseignant\n")
    n = proj[proj.annee_debut == HORIZON].groupby("scenario")[
        ["eleves_projetes", "salles_necessaires", "salles_a_construire", "salles_a_construire_avec_remplacement",
         "enseignants_necessaires", "enseignants_a_recruter"]].sum().astype(int).reindex(SCENARIOS)
    print(n.to_string())
    print("\nSensibilite aux normes (2030, national) - salles a construire / enseignants a recruter :")
    pv = sens.pivot_table(index=["norme_eleves_salle", "norme_eleves_enseignant"], columns="scenario",
                          values=["salles_a_construire", "enseignants_a_recruter"])
    print(pv.to_string())
    top = proj[(proj.annee_debut == HORIZON) & (proj.scenario == "retour_2020_2021")].nlargest(8, "salles_a_construire")
    print("\nTop 8 provinces - salles a construire, scenario retour_2020_2021 :")
    print(top[["province", "region_ancienne", "eleves_projetes", "nb_salles", "salles_a_construire", "enseignants_a_recruter"]]
          .round(0).astype({"eleves_projetes": int, "nb_salles": int, "salles_a_construire": int,
                            "enseignants_a_recruter": int}).to_string(index=False))


if __name__ == "__main__":
    main()
