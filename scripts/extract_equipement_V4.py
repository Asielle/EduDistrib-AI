"""Extraction du tableau "Equipement des ecoles" (V.4 ou VI.4 selon l'annee) des annuaires primaire (DGESS),
par province et par statut (Public / Prive / Total = Public+Prive) :
nombre d'ecoles fonctionnelles et nombre d'ecoles disposant d'eau potable, d'electricite, de latrines,
de jardins scolaires, de cantines, d'un terrain de sport, d'une cloture.

Le tableau est repere par son TITRE (le numero change selon l'annee).
Controles : ecoles fonctionnelles = nombre d'ecoles du tableau I.1 (a une tolerance pres), somme des provinces = total de la region,
aucun nombre d'ecoles equipees au-dessus du nombre d'ecoles.

Usage :
    python extract_equipement_V4.py <dossier_annuaires_csv> <admin2.csv> <tableau_I1_propre.csv> <sortie.csv>
"""
import csv
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_salles_VI import statut_du_titre, tolerance  # noqa: E402
from extract_tableau_I1 import annee_du_fichier, lire_lignes, num, region_canonique  # noqa: E402
from harmoniser_provinces import cle, construire_ref, lire_admin2  # noqa: E402

CHAMPS = ["ecoles", "eau_potable", "electricite", "latrines", "jardins", "cantines", "terrain_sport", "cloture"]


def extraire(chemin):
    annee = annee_du_fichier(os.path.basename(chemin))
    dans, statut, region = False, None, None
    out, ignorees = {}, 0
    for page, cells in lire_lignes(chemin):
        if not cells:
            continue
        t0 = cells[0]
        up = t0.upper()
        if len(cells) == 1 and t0 == up and re.match(r"^[IVX]+\.", up):          # titre numerote en majuscules
            dans = bool(re.search(r"EQUIPEMENT DES ECOLES", up))
            statut = None
            continue
        if len(cells) == 1 and re.match(r"^[IVX]+\.[\d.]+\s*\S", t0):             # sous-titre de statut
            s = statut_du_titre(t0)
            if s:
                statut = s
            continue
        if not dans or statut is None:
            continue
        if len(cells) == 1 and region_canonique(t0):
            region = region_canonique(t0)
            continue
        if up.startswith("%") or up.startswith("POURCENTAGE"):
            continue
        if len(cells) != len(CHAMPS) + 1:
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
        out[(annee, niveau, region or "", prov, statut)] = dict(zip(CHAMPS, vals))
    return out, ignorees


def main():
    dossier, admin2, i1_csv, sortie = sys.argv[1:5]
    par_cle = {cle(e["province"]): e for e in construire_ref(lire_admin2(admin2)).values()}
    with open(i1_csv, encoding="utf-8", newline="") as f:
        i1 = {}
        for r in csv.DictReader(f, delimiter=";"):
            niv = r["niveau"]
            prov = cle(r["province"]) if niv == "province" else ""
            reg = "" if niv == "national" else r["region_ancienne"]
            i1[(r["annee_scolaire"], niv, reg, prov, r["statut"])] = int(r["nb_ecoles"])
    toutes, ignorees = {}, 0
    for f in sorted(glob.glob(os.path.join(dossier, "*nseignement*rimaire*.csv"))):
        d, ign = extraire(f)
        ignorees += ign
        n_prov = len({k[3] for k in d if k[1] == "province" and k[4] == "Total"})
        print(f"{os.path.basename(f)[:70]:70} lignes={len(d):4} provinces(Total)={n_prov:2}")
        toutes.update(d)

    pb, mineurs = [], 0
    for k, d in toutes.items():
        an, niv, reg, prov, st = k
        ref = i1.get((an, niv, reg, cle(prov) if prov else "", st))
        if ref is not None and not tolerance(d["ecoles"], ref):
            pb.append(f"{k} ecoles fonctionnelles {d['ecoles']} != I.1 ({ref})")
        elif ref is not None and d["ecoles"] != ref:
            mineurs += 1
        for c in CHAMPS[1:]:
            if d[c] > d["ecoles"] * 1.02 + 2:
                pb.append(f"{k} {c} {d[c]} > ecoles {d['ecoles']}")
        if niv == "province" and cle(prov) not in par_cle:
            pb.append(f"province sans correspondance : {prov} ({an})")
    for k, d in toutes.items():
        an, niv, reg, prov, st = k
        if niv != "region":
            continue
        for c in CHAMPS:
            s = sum(x[c] for kk, x in toutes.items() if kk[0] == an and kk[1] == "province" and kk[2] == reg and kk[4] == st)
            if not tolerance(s, d[c]):
                pb.append(f"{an} {reg} {st} {c}: provinces {s} != region {d[c]}")
                break
    # Public + Prive = Total (au voisinage de 2 %)
    for k, d in toutes.items():
        if k[4] != "Total":
            continue
        pu, pr = toutes.get(k[:4] + ("Public",)), toutes.get(k[:4] + ("Prive",))
        if pu and pr:
            for c in CHAMPS:
                if not tolerance(pu[c] + pr[c], d[c]):
                    pb.append(f"{k} {c}: public {pu[c]} + prive {pr[c]} != total {d[c]}")
                    break

    os.makedirs(os.path.dirname(os.path.abspath(sortie)), exist_ok=True)
    with open(sortie, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["annee_scolaire", "niveau", "region_ancienne", "province_std", "pcode_province_old",
                    "pcodes_province_new", "statut", *[f"equip_{c}" for c in CHAMPS]])
        for k in sorted(toutes):
            an, niv, reg, prov, st = k
            e = par_cle.get(cle(prov)) if niv == "province" else None
            w.writerow([an, niv, reg, e["province"] if e else prov, e["pcode_old"] if e else "",
                        "|".join(e["pcodes_new"]) if e else "", st, *[toutes[k][c] for c in CHAMPS]])
    print(f"\n{len(toutes)} lignes -> {sortie} ; {ignorees} ligne(s) non numerique(s) ignoree(s) ; {mineurs} petit(s) ecart(s) avec I.1")
    print(f"{len(pb)} controle(s) en echec")
    for p in sorted(set(pb))[:30]:
        print("  -", p)


if __name__ == "__main__":
    main()
