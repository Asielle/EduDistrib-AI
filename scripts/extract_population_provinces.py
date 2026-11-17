"""Extraction des projections demographiques PROVINCIALES 2020-2035 (INSD, RGPH 2019, volume 4, chapitre 3).

Chaque province a 6 pages : 3 annees par bloc, 3 colonnes (Homme / Femme / Ensemble) par annee,
une ligne par groupe d'ages (0 an, 1-4, 3-5, 6-11, 12-15, ... 80 et +, Total).

Attention (methode de l'INSD, p. 199) : la structure par sexe et par age est supposee IDENTIQUE pour toutes les
provinces d'une meme region ; seul l'effectif total differe d'une province a l'autre.
Les groupes d'ages se chevauchent (1-4 et 3-5, 5-9 et 6-11) : ce sont des tranches utiles, pas une partition.

Entrees : CSV du rapport (Data Pack) + COD-AB adm2
Sortie  : CSV long (province, annee, groupe_age, sexe, valeur), relie aux P-codes des anciennes provinces

Usage :
    python extract_population_provinces.py <rapport.csv> <admin2.csv> <sortie.csv>
"""
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_tableau_I1 import lire_lignes, num  # noqa: E402
from harmoniser_provinces import ALIAS, cle, construire_ref, lire_admin2  # noqa: E402

# noms INSD differents des noms COD-AB (cle normalisee -> cle normalisee)
ALIAS_INSD = {"BALES": "BALE", "KOMONDJOARI": "KOMANDJARI", "KOMONDJARI": "KOMANDJARI",
              "KOURITENGA": "KOURITTENGA"}
SEXES = ["H", "F", "E"]
GROUPES = re.compile(r"^(\d+ an|\d+ ?- ?\d+ ans|\d+ ?-\d+ ans|80 ans et \+|Total)$", re.I)


def groupe_normalise(s):
    s = re.sub(r"\s+", "", s.lower())
    return s.replace("ans", "").replace("an", "").replace("et+", "+") if s != "total" else "total"


def extraire(chemin, debut_ligne=7457):
    """Retourne une liste de (nom_source, annee, groupe, sexe, valeur, page)."""
    out, nom, annees = [], None, []
    with open(chemin, encoding="utf-8", newline="") as f:
        lignes = list(f)
    # on rejoue lire_lignes sur le fichier entier, puis on ignore ce qui precede le chapitre provincial
    n = 0
    for page, cells in lire_lignes(chemin):
        n += 1
        if not cells:
            continue
        t0 = cells[0]
        if len(cells) == 1 and re.fullmatch(r"20[2-3]\d", t0):  # dernier bloc : une seule annee (2035)
            annees = [int(t0)]
            continue
        if len(cells) == 1:
            # nom de province = ligne seule, ni trait, ni pied de page, ni titre de chapitre
            if not re.match(r"^(_+|.*RGPH.*|PROVINCE\b.*|R[EÉ]GION\b.*|CHAPITRE.*|GROUPES?\b.*|\d+)$", t0, re.I) \
                    and len(t0) < 40:
                nom, annees = t0, []
            continue
        # ligne d'annees : "2020;2021;2022" ou "Groupes d'ages;2020;2021;2022"
        ann = [c for c in cells if re.fullmatch(r"20[2-3]\d", c)]
        if ann and len(ann) >= len(cells) - 1:
            annees = [int(a) for a in ann]
            continue
        if nom and annees and GROUPES.match(t0.strip()) and len(cells) == 1 + 3 * len(annees):
            vals = [num(c) for c in cells[1:]]
            if any(v is None for v in vals):
                continue
            g = groupe_normalise(t0)
            for i, a in enumerate(annees):
                for j, s in enumerate(SEXES):
                    out.append((nom, a, g, s, vals[3 * i + j], page))
    return out


def main():
    rapport, admin2, sortie = sys.argv[1:4]
    par_cle = {cle(e["province"]): e for e in construire_ref(lire_admin2(admin2)).values()}
    brut = extraire(rapport)
    noms = sorted({b[0] for b in brut})
    print(f"{len(noms)} noms de provinces trouves dans le rapport")

    correspondance, inconnus = {}, []
    for n in noms:
        k = cle(n)
        k = ALIAS_INSD.get(k, k)
        e = par_cle.get(k)
        if e:
            correspondance[n] = e
        else:
            inconnus.append(n)
    print("sans correspondance :", inconnus or "aucun")

    # un meme nom peut apparaitre sur plusieurs blocs : on garde la derniere valeur par (province, annee, groupe, sexe)
    dedup = {}
    for n, a, g, s, v, p in brut:
        if n in correspondance:
            dedup[(correspondance[n]["pcode_old"], a, g, s)] = (n, v, p)
    os.makedirs(os.path.dirname(os.path.abspath(sortie)), exist_ok=True)
    ref = {e["pcode_old"]: e for e in correspondance.values()}
    with open(sortie, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["pcode_province_old", "province", "nom_source_insd", "annee", "groupe_age", "sexe", "population", "page_pdf"])
        for (pc, a, g, s), (n, v, p) in sorted(dedup.items()):
            w.writerow([pc, ref[pc]["province"], n, a, g, s, v, p])

    provinces = {k[0] for k in dedup}
    annees = sorted({k[1] for k in dedup})
    groupes = sorted({k[2] for k in dedup})
    print(f"{len(dedup)} valeurs ; {len(provinces)} provinces ; annees {annees[0]}-{annees[-1]} ({len(annees)}) ; groupes d'ages : {groupes}")
    manquantes = [(ref[p]["province"], a) for p in provinces for a in annees if (p, a, "6-11", "E") not in dedup]
    print("provinces-annees sans 6-11 ans :", manquantes or "aucune")


if __name__ == "__main__":
    main()
