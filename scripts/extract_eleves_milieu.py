"""Extraction du tableau "Nombre d'eleves total, filles, % de filles, urbain et rural (public + prive)" des annuaires primaire,
par province (numerote I.2 ou II.2 selon l'annee).

Colonnes de chaque ligne source : urbain (total, filles, % filles), rural (total, filles, % filles), ensemble (total, filles, % filles).

Controles : urbain + rural = ensemble (eleves et filles) ; somme des provinces = total region ; regions = pays ;
ensemble = nombre d'eleves du tableau I.1 (public + prive) pour la meme province et la meme annee.

Usage :
    python extract_eleves_milieu.py <dossier_annuaires_csv> <admin2.csv> <tableau_I1_propre.csv> <enseignants_IV1_propre.csv> <sortie.csv>
"""
import csv
import glob
import os
import re
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_tableau_I1 import annee_du_fichier, lire_lignes, num, region_canonique  # noqa: E402
from harmoniser_provinces import cle, construire_ref, lire_admin2  # noqa: E402

CHAMPS = ["urbain_total", "urbain_filles", "urbain_pct_filles", "rural_total", "rural_filles", "rural_pct_filles",
          "ensemble_total", "ensemble_filles", "ensemble_pct_filles"]


def extraire(chemin):
    annee = annee_du_fichier(os.path.basename(chemin))
    dedans, region, ctx = False, None, None
    sortie = []
    for page, cells in lire_lignes(chemin):
        if not cells:
            continue
        t0 = cells[0]
        titre = len(cells) == 1 and t0 == t0.upper() and re.match(r"^[IVX]+\.", t0)
        if not dedans:
            if titre and re.match(r"^II?\.2\.? NOMBRE D'ELEVES TOTAL.*URBAIN ET RURAL", t0):
                dedans = True
            continue
        if titre and re.match(r"^II?\.[3-9]\b", t0):      # tableau suivant (I.3, I.4... ou II.3...) : fin du tableau
            break
        if len(cells) == 1 and region_canonique(t0):
            region, ctx = region_canonique(t0), None
            continue
        if len(cells) == 10:
            vals = [num(c) for c in cells[1:]]
            if any(v is None for v in vals):
                continue
            up = t0.upper()
            if up.startswith("TOTAL R"):
                niveau, prov = "region", ""
            elif up.startswith("TOTAL N") or up.startswith("BURKINA"):
                niveau, prov, region = "national", "", ""
            elif re.fullmatch(r"[A-ZÉÈÊÀÂÎÔÛÇ' \-]{3,}", up):
                niveau, prov = "province", up
            else:
                continue
        elif len(cells) == 9 and all(num(c) is not None for c in cells):   # ligne du pays sans nom
            vals, niveau, prov, region = [num(c) for c in cells], "national", "", ""
        elif len(cells) == 7 and re.fullmatch(r"[A-ZÉÈÊÀÂÎÔÛÇ' \-]{3,}", t0.upper()) and all(num(c) is not None for c in cells[1:]):
            # un seul milieu renseigne (l'autre est vide dans la source) : groupe 1 = ce milieu, groupe 2 = ensemble
            g = [num(c) for c in cells[1:]]
            up = t0.upper()
            niveau = "region" if up.startswith("TOTAL R") else "province"
            sortie.append({"annee_scolaire": annee, "niveau": niveau, "region_ancienne": region or "",
                           "province": "" if niveau == "region" else up, "milieu_unique": True,
                           **dict(zip(CHAMPS, g[:3] + [None] * 3 + g[3:])), "source_fichier": os.path.basename(chemin), "page_pdf": page})
            continue
        else:
            continue
        sortie.append({"annee_scolaire": annee, "niveau": niveau, "region_ancienne": region or "", "province": prov,
                       **dict(zip(CHAMPS, vals)), "source_fichier": os.path.basename(chemin), "page_pdf": page})
    return sortie


def resoudre_milieu_unique(df, ens_csv):
    """Quand la source ne renseigne qu'un milieu (l'autre est vide), on lit lequel d'apres les enseignants de la meme province et
    de la meme annee (tableaux IV.1.4 urbain et IV.1.5 rural) : un seul milieu a des enseignants. Si c'est ambigu, on laisse vide."""
    ens = pd.read_csv(ens_csv, sep=";", dtype={"pcode_province_old": str})
    ens = ens[(ens.niveau == "province") & (ens.sexe == "T") & ens.statut.isin(["Urbain", "Rural"])]
    nb = {(r.annee_scolaire, r.pcode_province_old, r.statut): r.nb_enseignants for r in ens.itertuples()}
    log = []
    for i, r in df[df["milieu_unique"] == True].iterrows():          # noqa: E712
        u, ru = nb.get((r.annee_scolaire, r.pcode_province_old, "Urbain"), 0), nb.get((r.annee_scolaire, r.pcode_province_old, "Rural"), 0)
        if u > 0 and ru == 0:
            cible = "urbain"
        elif ru > 0 and u == 0:
            cible = "rural"
        else:
            log.append(f"{r.annee_scolaire} {r.province}: milieu non determine (enseignants urbain {u}, rural {ru}) : laisse vide")
            continue
        for c in ("total", "filles", "pct_filles"):
            df.at[i, f"{cible}_{c}"] = r[f"urbain_{c}"]                 # le groupe lu en premier
        autre = "rural" if cible == "urbain" else "urbain"
        for c, v in (("total", 0.0), ("filles", 0.0), ("pct_filles", None)):
            df.at[i, f"{autre}_{c}"] = v
        log.append(f"{r.annee_scolaire} {r.province}: milieu unique = {cible} (enseignants urbain {u}, rural {ru})")
    return log


def controles(df, i1):
    pb = []
    for r in df.itertuples():
        if r.urbain_total != r.urbain_total or r.rural_total != r.rural_total:    # milieu non determine : pas de controle
            continue
        if r.urbain_total + r.rural_total != r.ensemble_total:
            pb.append(f"{r.annee_scolaire} {r.niveau} {r.province or r.region_ancienne}: urbain + rural != ensemble")
        if r.urbain_filles + r.rural_filles != r.ensemble_filles:
            pb.append(f"{r.annee_scolaire} {r.niveau} {r.province or r.region_ancienne}: filles urbain + rural != ensemble")
    for (an, reg), g in df[df.niveau == "province"].groupby(["annee_scolaire", "region_ancienne"]):
        tot = df[(df.annee_scolaire == an) & (df.niveau == "region") & (df.region_ancienne == reg)]
        if len(tot) and int(g.ensemble_total.sum()) != int(tot.ensemble_total.iloc[0]):
            pb.append(f"{an} {reg}: somme des provinces {int(g.ensemble_total.sum())} != total region {int(tot.ensemble_total.iloc[0])}")
    for an, g in df[df.niveau == "region"].groupby("annee_scolaire"):
        nat = df[(df.annee_scolaire == an) & (df.niveau == "national")]
        if len(nat) and int(g.ensemble_total.sum()) != int(nat.ensemble_total.iloc[0]):
            pb.append(f"{an}: somme des regions {int(g.ensemble_total.sum())} != total pays {int(nat.ensemble_total.iloc[0])}")
    m = df[df.niveau == "province"].merge(i1, on=["annee_scolaire", "province_cle"], how="left")
    for r in m.itertuples():
        if r.nb_eleves == r.nb_eleves and abs(r.ensemble_total - r.nb_eleves) > 0:
            pb.append(f"{r.annee_scolaire} {r.province}: ensemble milieu {int(r.ensemble_total)} != eleves I.1 {int(r.nb_eleves)}")
    return pb


def main():
    dossier, admin2, i1_csv, ens_csv, sortie = sys.argv[1:6]
    par_cle = {cle(e["province"]): e for e in construire_ref(lire_admin2(admin2)).values()}
    lignes = []
    for f in sorted(glob.glob(os.path.join(dossier, "*nseignement*rimaire*.csv"))):
        l = extraire(f)
        print(f"{os.path.basename(f)[:72]:72} lignes={len(l):3} provinces={len({x['province'] for x in l if x['niveau'] == 'province'})}")
        lignes += l
    df = pd.DataFrame(lignes)
    if "milieu_unique" not in df:
        df["milieu_unique"] = False
    df["milieu_unique"] = df["milieu_unique"].fillna(False).astype(bool)
    df["province_cle"] = [cle(p) if p else "" for p in df["province"]]
    df["pcode_province_old"] = [par_cle[k]["pcode_old"] if k in par_cle else "" for k in df["province_cle"]]
    for r in resoudre_milieu_unique(df, ens_csv):
        print("  milieu :", r)
    i1 = pd.read_csv(i1_csv, sep=";", dtype=str)
    i1 = i1[(i1.niveau == "province") & (i1.statut == "Total")].copy()
    i1["province_cle"] = [cle(p) for p in i1["province"]]
    i1["nb_eleves"] = pd.to_numeric(i1["nb_eleves"])
    pb = controles(df, i1[["annee_scolaire", "province_cle", "nb_eleves"]])
    df["province_std"] = [par_cle[k]["province"] if k in par_cle else p for k, p in zip(df["province_cle"], df["province"])]
    inconnus = sorted(set(df[(df.niveau == "province") & (df.pcode_province_old == "")]["province"]))
    if inconnus:
        pb.append(f"provinces sans correspondance : {inconnus}")
    cols = ["annee_scolaire", "niveau", "region_ancienne", "province_std", "pcode_province_old", *CHAMPS, "source_fichier", "page_pdf"]
    os.makedirs(os.path.dirname(os.path.abspath(sortie)), exist_ok=True)
    df[cols].to_csv(sortie, sep=";", index=False, encoding="utf-8")
    print(f"\n{len(df)} lignes -> {sortie}\n{len(pb)} controle(s) en echec")
    for p in sorted(set(pb))[:25]:
        print("  -", p)


if __name__ == "__main__":
    main()

