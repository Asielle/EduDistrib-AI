"""Extraction du tableau I.1 des annuaires statistiques de l'enseignement primaire (DGESS).

I.1 = nombre d'ecoles, de salles de classe, de groupes pedagogiques, de maitres,
d'eleves et ratio eleves/maitre, par province et par statut (Public / Prive / Total).

Entree  : CSV convertis depuis les PDF (Data Pack, dossier data/.../Annuaires)
Sortie  : un CSV "long" (une ligne = annee x province x statut) + un rapport de controle

Usage :
    python extract_tableau_I1.py <dossier_annuaires_csv> <fichier_sortie.csv>
"""
import csv
import glob
import os
import re
import sys

REGIONS = {
    "BOUCLE DU MOUHOUN", "CASCADES", "CENTRE", "CENTRE-EST", "CENTRE-NORD",
    "CENTRE-OUEST", "CENTRE-SUD", "EST", "HAUTS-BASSINS", "NORD",
    "PLATEAU-CENTRAL", "SAHEL", "SUD-OUEST",
}
STATUTS = {"public": "Public", "prive": "Prive", "privé": "Prive", "total": "Total"}
CHAMPS = ["nb_ecoles", "nb_salles", "nb_groupes", "nb_maitres", "nb_eleves", "ratio_eleves_maitre"]

csv.field_size_limit(10 ** 7)


_CANON = {re.sub(r"[\s\-]+", "", r): r for r in REGIONS}


def region_canonique(s):
    """'PLATEAU CENTRAL' / 'Plateau-Central' -> 'PLATEAU-CENTRAL' ; None si ce n'est pas une region."""
    return _CANON.get(re.sub(r"[\s\-]+", "", (s or "").upper()))


def norm(s):
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def num(s):
    """'1 143' -> 1143 ; '50,9' -> 50.9 ; sinon None."""
    t = norm(s).replace(" ", "").replace(",", ".")
    if not re.fullmatch(r"-?\d+(\.\d+)?", t):
        return None
    v = float(t)
    return int(v) if v.is_integer() and "." not in t else v


def annee_du_fichier(nom):
    m = re.search(r"(20\d\d)_(20\d\d)", nom)
    return f"{m.group(1)}-{m.group(2)}" if m else ""


def lire_lignes(chemin):
    with open(chemin, encoding="utf-8", newline="") as f:
        r = csv.reader(f, delimiter=";")
        next(r, None)  # en-tete ; la colonne remarque_collecte n'est pas utilisee
        for row in r:
            if len(row) < 5:
                continue
            page = row[1]
            # c1..c20 = colonnes 4..23 ; on retire les cellules vides de fin
            cells = [norm(c) for c in row[4:24]]
            while cells and cells[-1] == "":
                cells.pop()
            yield page, cells


def extraire(chemin):
    annee = annee_du_fichier(os.path.basename(chemin))
    dans_tableau, region, province, ctx = False, None, None, None
    sortie = []
    for page, cells in lire_lignes(chemin):
        if not cells:
            continue
        texte = cells[0].upper()
        # Titre de page en MAJUSCULES, seul sur sa ligne (la table des matieres est en
        # casse mixte et suivie d'un numero de page). Selon l'annee le tableau s'appelle
        # I.1 ou II.1 ; on exclut le tableau "43 communes prioritaires" (I.1 en 2017-2021).
        titre = len(cells) == 1 and cells[0] == texte
        if not dans_tableau:
            if titre and re.match(r"^II?\.1 NOMBRE D'ECOLES.*GROUPES PEDAGOGIQUES.*PAR STATUT", texte):
                dans_tableau = True
            continue
        if titre and re.match(r"^II?\.[2-9] ", texte):
            break
        if len(cells) == 1 and region_canonique(cells[0]):
            region, province = region_canonique(cells[0]), None
            continue

        # ligne "PROVINCE;Public;v1..v6" ou "Total Region;Public;..." (8 cellules)
        if len(cells) >= 8 and cells[1].lower() in STATUTS:
            nom, statut, vals = cells[0], STATUTS[cells[1].lower()], cells[2:8]
            if nom.upper().startswith("TOTAL R"):
                province, niveau = None, "region"
                ctx = "TOTAL REGION"
            elif nom.upper().startswith("TOTAL"):
                province, niveau = None, "national"
                ctx = "TOTAL NATIONAL"
            else:
                province, niveau, ctx = nom.upper(), "province", nom.upper()
        # lignes suivantes "Prive;v1..v6" / "Total;v1..v6" (7 cellules)
        elif len(cells) >= 7 and cells[0].lower() in STATUTS and num(cells[1]) is not None:
            statut, vals = STATUTS[cells[0].lower()], cells[1:7]
            if province:
                niveau = "province"
            elif ctx == "TOTAL REGION":
                niveau = "region"
            else:  # triplet Public/Prive/Total sans nom, apres le dernier "Total Region" : total pays
                niveau = "national"
        else:
            continue
        nums = [num(v) for v in vals]
        if any(n is None for n in nums):
            continue
        sortie.append({
            "annee_scolaire": annee,
            "region_ancienne": "" if niveau == "national" else (region or ""),
            "niveau": niveau,
            "province": ctx if niveau == "province" else "", "statut": statut,
            **dict(zip(CHAMPS, nums)),
            "source_fichier": os.path.basename(chemin), "page_pdf": page,
        })
        if statut == "Total" and niveau != "province":
            ctx = None  # le triplet region / national est termine
    return sortie


def controles(lignes):
    """Public + Prive = Total (ecoles, salles, eleves) ; somme des provinces = total region."""
    problemes = []
    idx = {}
    for l in lignes:
        cle = (l["annee_scolaire"], l["region_ancienne"], l["niveau"], l["province"])
        idx.setdefault(cle, {})[l["statut"]] = l
    for cle, d in idx.items():
        if {"Public", "Prive", "Total"} <= d.keys():
            for ch in ("nb_ecoles", "nb_salles", "nb_eleves"):
                if d["Public"][ch] + d["Prive"][ch] != d["Total"][ch]:
                    problemes.append(f"{cle} {ch}: {d['Public'][ch]}+{d['Prive'][ch]}!={d['Total'][ch]}")
        else:
            problemes.append(f"{cle} statuts incomplets: {sorted(d)}")
    for (an, reg, niv, _), d in list(idx.items()):
        if niv != "region" or "Total" not in d:
            continue
        for ch in ("nb_ecoles", "nb_salles", "nb_eleves"):
            s = sum(v["Total"][ch] for (a, r, n, p), v in idx.items()
                    if a == an and r == reg and n == "province" and "Total" in v)
            if s != d["Total"][ch]:
                problemes.append(f"{an} {reg} somme provinces {ch}={s} != total region {d['Total'][ch]}")
    for (an, _, niv, _), d in list(idx.items()):
        if niv != "national" or "Total" not in d:
            continue
        for ch in ("nb_ecoles", "nb_salles", "nb_eleves"):
            s = sum(v["Total"][ch] for (a, r, n, p), v in idx.items()
                    if a == an and n == "region" and "Total" in v)
            if s != d["Total"][ch]:
                problemes.append(f"{an} somme regions {ch}={s} != total pays {d['Total'][ch]}")
    return problemes


def main():
    dossier, sortie = sys.argv[1], sys.argv[2]
    toutes = []
    fichiers = sorted(glob.glob(os.path.join(dossier, "*nseignement*rimaire*.csv")))
    for f in fichiers:
        lignes = extraire(f)
        nprov = len({l["province"] for l in lignes if l["niveau"] == "province"})
        print(f"{os.path.basename(f)[:75]:75} lignes={len(lignes):4} provinces={nprov}")
        toutes += lignes
    os.makedirs(os.path.dirname(os.path.abspath(sortie)), exist_ok=True)
    cols = ["annee_scolaire", "region_ancienne", "niveau", "province", "statut", *CHAMPS,
            "source_fichier", "page_pdf"]
    with open(sortie, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=";")
        w.writeheader()
        w.writerows(toutes)
    pb = controles(toutes)
    print(f"\n{len(toutes)} lignes ecrites -> {sortie}")
    print(f"{len(pb)} controle(s) en echec")
    for p in pb[:40]:
        print("  -", p)


if __name__ == "__main__":
    main()
