# Plan du parcours des données

De la source publique au tableau de bord, en cinq étapes (les dossiers `01_collecte` à `05_interpretation`).

| Étape | Entrée | Traitement (script) | Sortie | Contrôle |
|---|---|---|---|---|
| **01 Collecte** | Data Pack du challenge (annuaires DGESS, INSD, CONASUR, COD-AB) et classeur DGESS 2016-2025 | Copie des fichiers bruts, sans modification. Chaque source est référencée (producteur, publication, année) | CSV et PDF bruts | Les totaux nationaux d'une série sont comparés aux publications d'origine |
| **02 Nettoyage** | CSV issus de PDF (tableaux à en-têtes multiples) | `extract_tableau_I1.py`, `extract_enseignants_IV1.py`, `extract_salles_VI.py`, `extract_equipement_V4.py`, `extract_eleves_milieu.py`, `extract_population_provinces.py`, `extract_pdi_conasur.py`, `harmoniser_provinces.py` | 8 tables propres | Public + privé = total ; provinces → régions → pays ; total des déplacés = chiffre CONASUR (écart nul) |
| **03 Transformation** | Tables propres | `build_panel.py` : jointure, ratios, parts, écarts à la norme | Panel de 360 lignes et dictionnaire | La somme des provinces égale exactement le total national |
| **04 Analyse** | Panel, population | `projection_2030.py`, `optimisation_2030.py`, `modele_predictif.py` | Projection 2030 (3 scénarios), optimisation, évaluation du modèle | Validation à origine glissante ; solution entière et flot maximal ; nivellement vérifié par dichotomie |
| **05 Interprétation** | Panel, projection, optimisation | `indice_tension.py`, `build_dashboard.py` | Indice de tension, tableau de bord HTML | Le calcul de la page est comparé au script Python : 135 valeurs et 108 cas, écart nul |

## Automatisation et reproduction

Chaque étape est un script Python indépendant, lancé dans l'ordre ci-dessus ; chaque script lit les sorties de l'étape précédente. Aucune étape manuelle. Dépendances : Python 3, `pandas`, `numpy`, `scipy`, `scikit-learn`, `Pillow` (logo) et Node.js (vérification). Commande de reconstruction : voir le `LISEZ-MOI.txt` de chaque dossier.

## Qualité, accès et protection

- **Qualité** : contrôles automatiques à chaque étape (liste ci-dessus), valeurs manquantes jamais comblées en silence, limites documentées dans chaque `LISEZ-MOI.txt`.
- **Traçabilité** : `source_fichier` et `page_pdf` sur chaque ligne extraite ; numérotation des versions (`v1`, `v2`…) dans les noms de dépôt.
- **Accès** : données publiques agrégées par province, aucune donnée personnelle ; les fichiers sont déposés dans l'espace de l'équipe sur equation.africadataentry.com ; les données ne servent qu'au concours.
- **Évolution** : pour ajouter une année, il suffit d'ajouter l'annuaire dans `01_collecte` et de relancer les scripts de bout en bout ; pour ajouter un niveau d'enseignement (post-primaire, secondaire), il faut ajouter un script d'extraction en étape 02.


