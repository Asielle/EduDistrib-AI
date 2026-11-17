"""Extraction des tableaux "caracteristiques et etat des locaux" des annuaires primaire (DGESS),
par province et par statut (Public / Prive / Total = Public+Prive) :

  annee    : salles de classe selon l'annee de mise en service      (9 colonnes)
  logement : ecoles disposant de logements de maitre               (4 colonnes)
  surface  : surface des salles de classe + eleves par classe        (8 colonnes)
  murs     : nature et etat des murs                                 (8 colonnes)
  toiture  : nature et etat des toitures                             (9 colonnes)

Les tableaux sont reperes par leur TITRE (le numero change selon l'annee : VI.x ou VII.x).
Sortie : un CSV large, une ligne = annee x lieu x statut, colonnes prefixees par tableau.

Usage :
    python extract_salles_VI.py <dossier_annuaires_csv> <admin2.csv> <tableau_I1_propre.csv> <sortie.csv>
"""
import csv
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_tableau_I1 import annee_du_fichier, lire_lignes, num, region_canonique  # noqa: E402
from harmoniser_provinces import cle, construire_ref, lire_admin2  # noqa: E402

TABLES = {
    "annee": (r"SELON L'ANNEE DE MISE EN SERVICE",
              ["avant_1965", "de_1965_1975", "de_1975_1985", "de_1985_1995", "de_1995_2005",
               "de_2005_2015", "apres_2015", "indetermine", "total"]),
    "log": (r"ECOLES DISPOSANT DE LOGEMENTS? DE MA",
            ["maitres", "ecoles_sans_logement", "logements", "logements_bon_etat"]),
    "surf": (r"SURFACE DES SALLES DE CLASSE",
             ["m2_moins_40", "m2_40_50", "m2_50_60", "m2_60_70", "m2_plus_70", "indetermine",
              "total", "eleves_par_classe"]),
    "murs": (r"NATURE ET ETAT DES MURS",
             ["en_dur", "semi_dur", "paille_banco_autre", "nature_indetermine",
              "etat_bon", "etat_mauvais", "etat_indetermine", "total"]),
    "toit": (r"NATURE ET ETAT DES TOITURES",
             ["tole_ciment", "tuiles", "banco", "paille", "sans_toit",
              "etat_bon", "etat_mauvais", "etat_indetermine", "total"]),
}
# Mise en page differente en 2017-2018 et 2018-2019 : pas de colonne "sans toit" (8 valeurs au lieu de 9)
TOIT_8 = ["tole_ciment", "tuiles", "banco", "paille", "etat_bon", "etat_mauvais", "etat_indetermine", "total"]


def tolerance(a, b):
    """Ecarts de la source elle-meme (arrondis, tableaux saisis separement) : <= 15 salles et <= 2 %."""
    return abs(a - b) <= max(15, 0.02 * max(a, b))


def statut_du_titre(texte):
    m = re.match(r"^[IVX]+\.[\d.]+\s*(.*)$", texte, re.I)
    if not m:
        return None
    t = m.group(1).lower().replace("é", "e").replace(" ", "")
    if t.startswith("public+priv"):
        return "Total"
    if t.startswith("public"):
        return "Public"
    if t.startswith("priv"):
        return "Prive"
    return None


def extraire(chemin):
    annee = annee_du_fichier(os.path.basename(chemin))
    table = statut = region = None
    out, ignorees = {}, 0
    for page, cells in lire_lignes(chemin):
        if not cells:
            continue
        t0 = cells[0]
        up = t0.upper()
        if len(cells) == 1 and t0 == up and re.match(r"^[IVX]+\.", up):  # titre numerote en majuscules
            for nom, (motif, _) in TABLES.items():
                if re.search(motif, up):
                    table, statut = nom, None
                    break
            else:
                table = table if re.search("|".join(m for m, _ in TABLES.values()), up) else None
                if not re.search(r"NATURE ET ETAT DES SALLES|CARACTERISTIQUES ET ETAT", up):
                    table = None
            continue
        if len(cells) == 1 and re.match(r"^[IVX]+\.[\d.]+\s*\S", t0):  # sous-titre de statut (casse mixte)
            s = statut_du_titre(t0)
            if s:
                statut = s
            continue
        if table is None or statut is None:
            continue
        if len(cells) == 1 and region_canonique(t0):
            region = region_canonique(t0)
            continue
        if up.startswith("%") or up.startswith("POURCENTAGE"):
            continue
        champs = TABLES[table][1]
        if table == "toit" and len(cells) == len(TOIT_8) + 1:
            champs = TOIT_8
        if len(cells) != len(champs) + 1:
            continue
        vals = [num(c) for c in cells[1:]]
        if any(v is None for v in vals):
            ignorees += 1
            continue
        if up.startswith("TOTAL R"):
            niveau, prov = "region", ""
        elif up.startswith("TOTAL N"):
            niveau, region, prov = "national", "", ""
        elif re.fullmatch(r"[A-ZÉÈÊÀÂÎÔÛÇ' \-]{3,}", up):
            niveau, prov = "province", up
        else:
            continue
        key = (annee, niveau, region or "", prov, statut)
        out.setdefault(key, {}).update({f"{table}_{c}": v for c, v in zip(champs, vals)})
    return out, ignorees


def controles(lignes, i1):
    pb = []
    for k, d in lignes.items():
        an, niv, reg, prov, st = k
        # coherence interne : tous les "total" des tableaux = meme nombre de salles
        tot = {t: d[f"{t}_total"] for t in ("annee", "surf", "murs", "toit") if f"{t}_total" in d}
        if tot and not tolerance(min(tot.values()), max(tot.values())):
            pb.append(f"{k} totaux de salles differents entre tableaux : {tot}")
        else:
            if tot and min(tot.values()) != max(tot.values()):
                MINEURS.append(k)
        # coherence avec le tableau I.1 (nombre de salles de classe)
        ref = i1.get(k)
        if ref and tot and any(not tolerance(v, ref[0]) for v in tot.values()):
            pb.append(f"{k} salles {tot} != I.1 ({ref[0]})")
        if ref and "log_maitres" in d and not tolerance(d["log_maitres"], ref[1]):
            pb.append(f"{k} maitres logement {d['log_maitres']} != I.1 ({ref[1]})")
    # somme des provinces = total region
    for k, d in lignes.items():
        an, niv, reg, prov, st = k
        if niv != "region":
            continue
        for col, v in d.items():
            if col.endswith(("eleves_par_classe",)):
                continue
            s = sum(x.get(col, 0) for kk, x in lignes.items()
                    if kk[0] == an and kk[1] == "province" and kk[2] == reg and kk[4] == st)
            if not tolerance(s, v):
                pb.append(f"{an} {reg} {st} {col}: provinces {s} != region {v}")
                break
    return pb


MINEURS = []  # ecarts minimes entre tableaux (la source n'est pas parfaitement coherente)


def main():
    dossier, admin2, i1_csv, sortie = sys.argv[1:5]
    par_cle = {cle(e["province"]): e for e in construire_ref(lire_admin2(admin2)).values()}
    with open(i1_csv, encoding="utf-8", newline="") as f:
        i1 = {}
        for r in csv.DictReader(f, delimiter=";"):
            niv = r["niveau"]
            prov = r["province"].upper() if niv == "province" else ""
            reg = "" if niv == "national" else r["region_ancienne"]
            i1[(r["annee_scolaire"], niv, reg, prov, r["statut"])] = (int(r["nb_salles"]), int(r["nb_maitres"]))
    # I.1 donne des noms harmonises (ex. Balé) : on indexe aussi par cle normalisee
    i1 = {(a, n, rg, cle(p) if p else "", s): v for (a, n, rg, p, s), v in i1.items()}

    toutes, ignorees = {}, 0
    for f in sorted(glob.glob(os.path.join(dossier, "*nseignement*rimaire*.csv"))):
        d, ign = extraire(f)
        ignorees += ign
        n_prov = len({k[3] for k in d if k[1] == "province"})
        par_table = {t: sum(1 for x in d.values() if any(c.startswith(t + "_") for c in x)) for t in TABLES}
        print(f"{os.path.basename(f)[:70]:70} cles={len(d):4} provinces={n_prov:2} {par_table}")
        toutes.update(d)

    # cles normalisees pour la comparaison avec I.1 (provinces)
    norm = {(a, n, rg, cle(p) if p else "", s): v for (a, n, rg, p, s), v in toutes.items()}
    pb = controles(norm, i1)
    pb += [f"province sans correspondance : {k[3]} ({k[0]})" for k in toutes
           if k[1] == "province" and cle(k[3]) not in par_cle]

    colonnes = [f"{t}_{c}" for t, (_, cs) in TABLES.items() for c in cs]
    os.makedirs(os.path.dirname(os.path.abspath(sortie)), exist_ok=True)
    with open(sortie, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["annee_scolaire", "niveau", "region_ancienne", "province_std", "pcode_province_old",
                    "pcodes_province_new", "statut", *colonnes])
        for k in sorted(toutes):
            an, niv, reg, prov, st = k
            e = par_cle.get(cle(prov)) if niv == "province" else None
            w.writerow([an, niv, reg, e["province"] if e else prov, e["pcode_old"] if e else "",
                        "|".join(e["pcodes_new"]) if e else "", st, *[toutes[k].get(c, "") for c in colonnes]])
    print(f"\n{len(toutes)} lignes -> {sortie} ; {ignorees} ligne(s) non numeriques ignoree(s)")
    print(f"{len(MINEURS)} groupe(s) avec un petit ecart (<= 15 salles et <= 2 %) entre tableaux de la source")
    print(f"{len(pb)} controle(s) en echec")
    for p in sorted(set(pb))[:30]:
        print("  -", p)


if __name__ == "__main__":
    main()
