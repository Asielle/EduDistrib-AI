"""Harmonisation des provinces : noms DGESS (13 anciennes regions, 45 provinces) <-> COD-AB (17 regions, 47 provinces).

Entrees : bfa_admin_boundaries__bfa_admin2.csv (COD-AB, colonnes *_old = ancien decoupage)
          tableau_I1_brut.csv (sortie de extract_tableau_I1.py)
Sorties : ref_provinces.csv        table de correspondance (1 ligne = 1 ancienne province)
          tableau_I1_propre.csv    tableau I.1 avec noms normalises et P-codes

Unite d'analyse retenue : l'ANCIENNE province (45), car toutes les donnees DGESS sont a ce niveau.
Soum (-> Djelgodji + Karo-Peli) et Tapoa (-> Dyamongou + Gobnangou) ont ete scindees dans le
nouveau decoupage : elles gardent plusieurs P-codes nouveaux, et une seule region nouvelle.

Usage :
    python harmoniser_provinces.py <admin2.csv> <tableau_I1_brut.csv> <dossier_sortie>
"""
import csv
import os
import re
import sys
import unicodedata

# Noms DGESS differents du nom COD-AB de l'ancienne province (cle normalisee -> cle normalisee)
ALIAS = {"LESBALE": "BALE", "KOMONDJARI": "KOMANDJARI"}


def cle(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    k = re.sub(r"[^A-Z0-9]", "", s.upper())
    return ALIAS.get(k, k)


def lire_admin2(chemin):
    with open(chemin, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f, delimiter=";"))
    entete = rows[1]  # ligne 1 = col1..colN (artefact de conversion), ligne 2 = vrais noms de colonnes
    return [dict(zip(entete, r)) for r in rows[2:] if len(r) > 5 and r[4]]


def construire_ref(admin2):
    ref = {}
    for r in admin2:
        po = r["adm2_pcode_old"]
        e = ref.setdefault(po, {
            "pcode_old": po, "province": r["adm2_name_old"],
            "pcodes_new": [], "provinces_new": [],
            "pcode_region_new": r["adm1_pcode"], "region_new": r["adm1_name"], "superficie_km2": 0.0,
        })
        e["superficie_km2"] += float(r.get("area_sqkm") or 0)       # une province scindee : somme des deux parties
        e["pcodes_new"].append(r["adm2_pcode"])
        e["provinces_new"].append(r["adm2_name"])
        assert e["pcode_region_new"] == r["adm1_pcode"], f"{po} a cheval sur deux regions nouvelles"
    return ref


def main():
    admin2, brut, sortie = sys.argv[1:4]
    ref = construire_ref(lire_admin2(admin2))
    par_cle = {cle(e["province"]): e for e in ref.values()}
    os.makedirs(sortie, exist_ok=True)

    with open(brut, encoding="utf-8", newline="") as f:
        lignes = list(csv.DictReader(f, delimiter=";"))

    # region ancienne de chaque province, d'apres les donnees DGESS
    reg_old = {}
    for l in lignes:
        if l["niveau"] == "province":
            reg_old.setdefault(cle(l["province"]), set()).add(l["region_ancienne"])

    non_trouves, sortie_lignes = set(), []
    for l in lignes:
        e = par_cle.get(cle(l["province"])) if l["niveau"] == "province" else None
        if l["niveau"] == "province" and e is None:
            non_trouves.add(l["province"])
        sortie_lignes.append({
            "annee_scolaire": l["annee_scolaire"], "niveau": l["niveau"],
            "region_ancienne": l["region_ancienne"],
            "province": e["province"] if e else l["province"],
            "pcode_province_old": e["pcode_old"] if e else "",
            "pcodes_province_new": "|".join(e["pcodes_new"]) if e else "",
            "region_nouvelle": e["region_new"] if e else "",
            "pcode_region_nouvelle": e["pcode_region_new"] if e else "",
            "statut": l["statut"], "nb_ecoles": l["nb_ecoles"], "nb_salles": l["nb_salles"],
            "nb_groupes": l["nb_groupes"], "nb_maitres": l["nb_maitres"], "nb_eleves": l["nb_eleves"],
            "ratio_eleves_maitre": l["ratio_eleves_maitre"],
            "source_fichier": l["source_fichier"], "page_pdf": l["page_pdf"],
        })

    with open(os.path.join(sortie, "tableau_I1_propre.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(sortie_lignes[0]), delimiter=";")
        w.writeheader()
        w.writerows(sortie_lignes)

    with open(os.path.join(sortie, "ref_provinces.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["pcode_province_old", "province", "region_ancienne_dgess", "pcodes_province_new",
                    "provinces_new", "pcode_region_nouvelle", "region_nouvelle", "scindee", "superficie_km2"])
        for po, e in sorted(ref.items()):
            ra = "|".join(sorted(reg_old.get(cle(e["province"]), {"?"})))
            w.writerow([po, e["province"], ra, "|".join(e["pcodes_new"]), "|".join(e["provinces_new"]),
                        e["pcode_region_new"], e["region_new"], "oui" if len(e["pcodes_new"]) > 1 else "non", round(e["superficie_km2"], 1)])

    couvertes = {cle(l["province"]) for l in lignes if l["niveau"] == "province"}
    jamais = [e["province"] for k, e in par_cle.items() if k not in couvertes]
    print(f"{len(ref)} anciennes provinces COD-AB -> {sum(len(e['pcodes_new']) for e in ref.values())} provinces nouvelles")
    print(f"noms DGESS sans correspondance : {sorted(non_trouves) or 'aucun'}")
    print(f"provinces COD-AB absentes des donnees DGESS : {jamais or 'aucune'}")
    print(f"lignes ecrites : {len(sortie_lignes)}")


if __name__ == "__main__":
    main()
