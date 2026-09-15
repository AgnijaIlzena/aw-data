"""Bilingue EN/FR pour le tableau de bord.

La clé de traduction est la chaîne anglaise elle-même : une chaîne absente du
dictionnaire retombe sur l'anglais au lieu d'afficher un identifiant technique.
Le module ne connaît ni Streamlit ni les données — `set_lang` est appelé une
fois par l'application, au moment où l'utilisateur choisit la langue.
"""
from __future__ import annotations

LANGS = {"en": "English", "fr": "Français"}

_lang = "en"


def set_lang(code: str) -> None:
    global _lang
    _lang = code if code in LANGS else "en"


def get_lang() -> str:
    return _lang


def t(s: str) -> str:
    """Traduit `s`, ou le renvoie inchangé si aucune traduction n'existe."""
    if _lang == "en":
        return s
    return FR.get(" ".join(s.split()), s)


FR: dict[str, str] = {
    # -- navigation --------------------------------------------------------
    "Overview": "Vue d'ensemble",
    "The gap": "Le fossé",
    "What predicts the gap": "Ce qui explique le fossé",
    "Resilience horizon": "Horizon de résilience",
    "Item bank": "Banque d'items",
    "Country vs Europe": "Pays et Europe",
    "Composite (live weights)": "Composite (pondération réglable)",
    "Method & limitations": "Méthode et limites",
    "US comparison (FEMA)": "Comparaison États-Unis (FEMA)",
    "Page": "Page",
    "Language": "Langue",
    "Readiness indices from Eurobarometer ZA8841":
        "Indices de préparation, Eurobaromètre ZA8841",
    "Every figure is read from DuckDB. This dashboard never recomputes an index — "
    "the pipeline is the only place they are defined.":
        "Chaque chiffre est lu dans DuckDB. Ce tableau de bord ne recalcule jamais un "
        "indice — le pipeline est le seul endroit où ils sont définis.",

    # -- Vue d'ensemble ----------------------------------------------------
    "The knowing–doing gap": "Le fossé entre savoir et faire",
    "Europeans know what to do to prepare for a crisis. Most still haven't done it. "
    "Eurobarometer ZA8841 · 26,405 respondents · 27 Member States · "
    "fieldwork Feb–Mar 2024":
        "Les Européens savent quoi faire pour se préparer à une crise. La plupart ne "
        "l'ont pas fait. Eurobaromètre ZA8841 — 26 405 répondants — 27 États "
        "membres — terrain février-mars 2024",
    "Every person × measure falls in one of four cells":
        "Chaque couple personne × action tombe dans une case sur quatre",
    "Readiness by country": "Préparation par pays",

    # -- Le fossé ----------------------------------------------------------
    "Which measures information actually converts":
        "Quelles actions l'information déclenche réellement",
    "Conversion versus lift": "Conversion et effet de levier",
    "**Conversion** = of those who saw information, how many acted. **Lift** = how "
    "many times more likely to have acted if aware. High lift with low conversion is "
    "where information helps but is not enough — and where a guided tool beats a "
    "leaflet.":
        "**Conversion** = parmi ceux qui ont vu de l'information, combien ont agi. "
        "**Levier** = combien de fois plus susceptibles d'avoir agi quand on est "
        "informé. Un levier élevé avec une conversion faible, c'est là où l'information "
        "aide sans suffire — et là où un outil guidé fait mieux qu'une brochure.",
    "Per measure": "Action par action",

    # -- Ce qui explique le fossé ------------------------------------------
    "Not how big the gap is — Phase 3 answers that — but *why* someone sits "
    "in it. Two candidate explanations are measured separately by the survey: "
    "**qc8_3**, no time or money to prepare, and **qc8_5**, needs more information. "
    "They imply opposite products, so telling them apart matters.":
        "Non pas l'ampleur du fossé — la phase 3 y répond — mais *pourquoi* "
        "quelqu'un s'y trouve. L'enquête mesure séparément deux explications possibles : "
        "**qc8_3**, ni le temps ni les moyens de se préparer, et **qc8_5**, besoin de "
        "plus d'information. Elles impliquent des produits opposés : les distinguer est "
        "donc décisif.",
    "Every model beside its baseline": "Chaque modèle face à sa référence",
    "Ranked by SHAP — how much each factor moves the prediction":
        "Classement SHAP — de combien chaque facteur déplace la prédiction",
    "SHAP opens the model back up after fitting: for every prediction, it assigns each "
    "feature a share of the credit or blame. The bars are the average size of that "
    "contribution, ranked — this is what turns a black-box prediction into a "
    "stated, checkable finding.":
        "SHAP rouvre le modèle une fois entraîné : pour chaque prédiction, il attribue à "
        "chaque variable une part de responsabilité. Les barres donnent la taille moyenne "
        "de cette contribution, classée — c'est ce qui transforme une prédiction "
        "opaque en résultat énoncé et vérifiable.",
    "The two barriers, head to head": "Les deux freins, face à face",

    # -- Horizon de résilience ---------------------------------------------
    "Resilience horizon — how long a household could cope":
        "Horizon de résilience — combien de temps un foyer tiendrait",
    "Distribution of the weakest lifeline": "Distribution du maillon faible",
    "Which lifeline runs out first": "Quelle ressource s'épuise en premier",
    "Country ranking — most exposed first":
        "Classement des pays — les plus exposés d'abord",
    "Reported as a range, not a point: the '2–3 days' band straddles the 72-hour "
    "target, so the true share below target lies between these two columns.":
        "Présenté comme une fourchette et non comme un point : la tranche "
        "« 2-3 jours » chevauche la cible de 72 heures, donc la part réellement "
        "sous la cible se situe entre ces deux colonnes.",

    # -- Banque d'items ----------------------------------------------------
    "Item bank — what each measure tells us":
        "Banque d'items — ce que chaque action nous apprend",
    "2PL item response theory. **Difficulty** is how far along the trait you must be "
    "before the measure becomes likely; **discrimination** is how sharply it separates "
    "prepared from unprepared.":
        "Modèle de réponse à l'item à deux paramètres. La **difficulté** indique jusqu'où "
        "il faut être avancé sur le trait pour que l'action devienne probable ; la "
        "**discrimination** indique avec quelle netteté elle sépare les foyers préparés "
        "des autres.",
    "The battery measures two things, not one": "La batterie mesure deux choses, pas une",
    "Discrimination splits cleanly into a sharp group (supplies you buy and store) and a "
    "flat group (things you do and arrange). 2PL assumes a single trait, so PRI is "
    "dominated by the sharp group. A two-dimensional model is the principled next step.":
        "La discrimination se sépare nettement en un groupe marqué (les fournitures qu'on "
        "achète et qu'on stocke) et un groupe plat (les choses qu'on fait et qu'on "
        "organise). Le modèle à deux paramètres suppose un trait unique, donc le PRI est "
        "dominé par le premier groupe. Un modèle à deux dimensions est la suite logique.",
    "Item fit": "Ajustement des items",
    "Productive range is 0.5–1.5. All 13 items fall inside it.":
        "La plage utile va de 0,5 à 1,5. Les treize items s'y trouvent tous.",

    # -- Pays et Europe ----------------------------------------------------
    "Country versus Europe": "Le pays face à l'Europe",
    "Negative means the action is *more common* there than the European average, "
    "positive means rarer. This is the shape of a country's preparedness culture, not "
    "its overall level.":
        "Une valeur négative signifie que l'action y est *plus répandue* que la moyenne "
        "européenne, une valeur positive qu'elle y est plus rare. C'est la forme de la "
        "culture de préparation d'un pays, pas son niveau général.",
    "PRI percentiles — the benchmark the product shows":
        "Percentiles du PRI — le repère affiché dans le produit",

    # -- Composite ---------------------------------------------------------
    "Composite readiness — how much should each index count?":
        "Préparation composite — combien doit compter chaque indice ?",
    "The three indices measure different things: how much you have done (PRI), how long "
    "you could last (RHI), and how much of what you know about you have skipped (PGI). "
    "Weighting them is a judgement, not a fact — so it is exposed rather than hidden.":
        "Les trois indices mesurent des choses différentes : ce que vous avez fait (PRI), "
        "combien de temps vous tiendriez (RHI), et la part de ce que vous connaissiez que "
        "vous n'avez pas fait (PGI). Les pondérer relève du jugement, pas du fait — "
        "c'est donc exposé plutôt que caché.",
    "Set at least one weight above zero.":
        "Mettez au moins une pondération au-dessus de zéro.",
    "Move the sliders. The ranking re-sorts live — which is the point: the ordering "
    "is a consequence of a weighting choice, and the choice is visible.":
        "Déplacez les curseurs. Le classement se réordonne en direct — et c'est le "
        "propos : l'ordre découle d'un choix de pondération, et ce choix est visible.",

    # -- FEMA --------------------------------------------------------------
    "United States comparison — item-level conversion":
        "Comparaison États-Unis — conversion action par action",
    "FEMA's National Household Survey asks awareness and action over the *same* twelve "
    "measures, so conversion can be computed per message. Europe asks awareness once, "
    "globally — which is why this cannot be done on EB547.":
        "L'enquête nationale de la FEMA interroge la connaissance et l'action sur les "
        "*mêmes* douze actions, si bien que la conversion se calcule message par message. "
        "L'Europe pose la question de la connaissance une seule fois, globalement — "
        "c'est pourquoi ce calcul est impossible sur l'EB547.",
    "Stage of change": "Stade de changement",
    "A validated intention→action ladder with no EB547 equivalent — the "
    "empirical grounding for the avatar's progression.":
        "Une échelle intention→action validée, sans équivalent dans l'EB547 — le "
        "fondement empirique de la progression de l'avatar.",
    "Europe versus United States": "Europe et États-Unis",
    "**Comparison only, never pooled.** FEMA measures a 12-month flow; EB547 measures a "
    "lifetime stock. Directions are comparable; levels are not.":
        "**Comparaison seulement, jamais d'agrégation.** La FEMA mesure un flux sur douze "
        "mois ; l'EB547 mesure un stock accumulé sur la vie entière. Les tendances sont "
        "comparables, les niveaux ne le sont pas.",
    "FEMA NHS is a **repeated cross-section** — roughly 5,000 different people each "
    "year, not a panel. Any trend here is an aggregate trend; nothing in this data "
    "supports predicting an individual's transition from aware to acted.":
        "L'enquête FEMA est une **coupe transversale répétée** — environ 5 000 "
        "personnes différentes chaque année, et non un panel. Toute tendance visible ici "
        "est agrégée ; rien dans ces données ne permet de prédire le passage d'un individu "
        "de la connaissance à l'action.",

    # -- Méthode et limites ------------------------------------------------
    "Method, and what this cannot tell you": "Méthode, et ce que ceci ne peut pas dire",
    "The gate": "La porte de cohérence",
    "Nothing downstream was trusted until the pipeline reproduced figures the European "
    "Commission published from this same survey — all seven within ±0.6 points.":
        "Rien en aval n'a été considéré comme fiable tant que le pipeline n'a pas reproduit "
        "les chiffres publiés par la Commission européenne à partir de cette même enquête "
        "— les sept à ±0,6 point près.",
    "Driver model against its baselines": "Le modèle explicatif face à ses références",
    "Grouped 5-fold CV by country. Demographics alone score *below* the mean predictor "
    "— who you are barely predicts preparedness.":
        "Validation croisée en cinq blocs, groupée par pays. La démographie seule fait "
        "*moins bien* que la prédiction moyenne — qui vous êtes ne prédit presque pas "
        "votre préparation.",
    "Ordered probit on the horizon bands": "Probit ordonné sur les tranches d'horizon",
    "Two of five domains do not beat their baseline. Reported, not hidden.":
        "Deux domaines sur cinq ne battent pas leur référence. Signalé, pas dissimulé.",
    "Limitations": "Limites",

    # -- encarts et notes de lecture ---------------------------------------
    "**gap** = saw information, did not act. The largest single cell, and the "
    "addressable one.":
        "**fossé** = a vu l'information, n'a pas agi. La case la plus nombreuse, "
        "et la seule sur laquelle un produit peut agir.",
    "**Tested on countries the model never trained on.** 5-fold cross-validation, "
    "grouped by country rather than split at random, so a country's whole data is held "
    "out in each round and predicted blind. The R² above is computed only from those "
    "held-out predictions — never from data the model was trained on. Demographics "
    "alone score *below* zero, i.e. worse than a flat average; only adding the barrier "
    "and attitude questions makes the model useful.":
        "**Testé sur des pays que le modèle n'a jamais vus à l'entraînement.** "
        "Validation croisée en cinq blocs, groupée par pays plutôt que découpée au "
        "hasard : à chaque tour, toutes les données d'un pays sont mises de côté et "
        "prédites à l'aveugle. Le R² ci-dessus ne vient que de ces prédictions hors "
        "échantillon — jamais de données vues à l'entraînement. La démographie seule "
        "obtient un score *négatif*, donc pire qu'une moyenne plate ; seules les "
        "questions de freins et d'attitudes rendent le modèle utile.",
    "Water and power are ~91% of all binding constraints. Food is under 2% — yet food "
    "is the most commonly stockpiled item.":
        "L'eau et l'électricité représentent environ 91 % des contraintes limitantes. "
        "La nourriture est sous les 2 % — alors que c'est ce qu'on stocke le plus.",
    "No focus country has been scored yet — run scripts/run_holdout.py.":
        "Aucun pays suivi n'a encore été évalué — lancez scripts/run_holdout.py.",
    "Age bands flagged `thin_cell` are built on fewer than 100 effective respondents. "
    "Show the national figure there instead of the band.":
        "Les tranches d'âge marquées `thin_cell` reposent sur moins de 100 répondants "
        "effectifs. Affichez-y le chiffre national plutôt que celui de la tranche.",
    "- **Self-reported throughout.** Nobody checked a cupboard. These are *perceived* "
    "horizons and *claimed* measures. - **One snapshot, February–March 2024.** No trend, "
    "no causal design. - **Association, not causation.** People who saw information and "
    "acted may simply be the sort of people who do both. - **Latvia is 1,008 "
    "respondents.** Enough for national figures, thin once split by age — bands below "
    "100 respondents are flagged in the tables. - **The action battery has no time "
    "window.** It asks what you have *already* adopted, so it is a lifetime stock, not a "
    "12-month flow. It is not comparable to FEMA's equivalent without adjustment. - "
    "**The battery is not unidimensional** (see Item bank). PRI is dominated by the "
    "supplies items.":
        "- **Tout est déclaratif.** Personne n'a vérifié un placard. Ce sont des "
        "horizons *perçus* et des actions *déclarées*.\n"
        "- **Un seul instantané, février-mars 2024.** Aucune tendance, aucun dispositif "
        "causal.\n"
        "- **Association, pas causalité.** Les personnes qui ont vu de l'information et "
        "agi sont peut-être simplement celles qui font les deux.\n"
        "- **La Lettonie, c'est 1 008 répondants.** Assez pour des chiffres nationaux, "
        "peu une fois ventilé par âge — les tranches sous 100 répondants sont signalées "
        "dans les tableaux.\n"
        "- **La batterie d'actions n'a pas de fenêtre temporelle.** Elle demande ce que "
        "vous avez *déjà* adopté : c'est un stock accumulé, pas un flux sur douze mois. "
        "Elle n'est pas comparable à son équivalent FEMA sans ajustement.\n"
        "- **La batterie n'est pas unidimensionnelle** (voir Banque d'items). Le PRI est "
        "dominé par les items de fournitures.",

    # -- étiquettes de graphiques ------------------------------------------
    "share of observations": "part des observations",
    "mean PRI (0–100)": "PRI moyen (0-100)",
    "conversion P(acted | aware)": "conversion P(a agi | informé)",
    "lift (× more likely)": "levier (× plus probable)",
    "lift": "levier",
    "mean |SHAP value| (average influence on the prediction)":
        "|SHAP| moyen (influence moyenne sur la prédiction)",
    "share of households": "part des foyers",
    "share of households where it binds": "part des foyers où elle est limitante",
    "share of households below target": "part des foyers sous la cible",
    "difficulty (b)": "difficulté (b)",
    "discrimination (a)": "discrimination (a)",
    "difficulty difference (native − pooled)":
        "écart de difficulté (national − agrégé)",
    "composite readiness (0–100)": "préparation composite (0-100)",
    "conversion P(did | aware of this measure)":
        "conversion P(a fait | informé de cette action)",
}
