"""
generate_demo_data.py
======================

Genere un jeu de donnees de demonstration realiste pour la PME fictive
"Atlas Distribution" (negoce, ~2 M EUR de CA annuel, 12 mois d'historique),
utilise par le workflow n8n "CFO Virtuel".

Sortie (CSV, dans ./output) :
  - transactions_bancaires.csv   (date, libelle, montant, categorie)
  - factures_clients.csv         (numero, client, montant, date_emission, date_echeance, date_paiement)
  - factures_fournisseurs.csv    (numero, fournisseur, montant, date_emission, date_echeance, date_paiement)
  - charges_recurrentes.csv      (libelle, categorie, montant, frequence, prochaine_echeance, intervalle_jours)
  - solde_bancaire_depart.csv    (date, solde, libelle)

Anomalies volontairement injectees (detaillees dans ANOMALIES.md genere en sortie) :
  1. Degradation progressive du delai de paiement du client "Meunier Negoce"
     sur les 4 derniers mois d'emission de factures.
  2. Depense inhabituelle en categorie "Frais generaux" (reparation vehicule
     en urgence), montant > moyenne + 2 ecarts-types de la categorie.
  3. Semaine de tresorerie tendue a venir : convergence du loyer trimestriel,
     d'une echeance d'emprunt/abonnements et d'une grosse commande fournisseur
     exceptionnelle (reappro Global Import SA) sur la meme semaine.
  Bonus (consequence naturelle de l'anomalie 1) : la derniere facture du
  client "Meunier Negoce" reste ouverte et fortement en retard a la date du jour.

Deterministe : seed fixe (RANDOM_SEED) -> resultats reproductibles entre les runs.

Simplifications documentees (voir README de la Phase 4) :
  - Montants exprimes TTC (pas de modelisation separee de la TVA/URSSAF).
  - Les charges mensuelles sont projetees a intervalle fixe (~30 jours), donc
    la date exacte ("le 5 du mois") peut deriver de quelques jours sur
    l'horizon de 13 semaines. Suffisant pour la demo ; a affiner en reel
    avec une regle "jour calendaire du mois".
"""

import calendar
import csv
import random
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Parametres generaux
# ---------------------------------------------------------------------------

RANDOM_SEED = 42
random.seed(RANDOM_SEED)

TODAY = date(2026, 9, 27)                    # ancre = "aujourd'hui" (jour d'execution du workflow)
HIST_START = date(2025, 10, 1)               # debut de l'historique (12 mois)
HIST_END = TODAY - timedelta(days=1)         # fin de l'historique = veille du jour d'execution
FORECAST_WEEKS = 13
FORECAST_END = TODAY + timedelta(weeks=FORECAST_WEEKS)

SOLDE_DEPART = 35_000.0                      # solde bancaire d'ouverture (fixe, plausible pour la PME)

OUT_DIR = Path(__file__).parent / "output"

CATEGORIES_CHARGES = {
    "loyer": "Loyer",
    "salaires": "Salaires",
    "emprunt": "Emprunt",
    "abonnements": "Abonnements",
    "assurance": "Frais generaux",
}


def add_months(d: date, n: int) -> date:
    """Ajoute n mois a une date, en bornant le jour au nombre de jours du mois cible."""
    month_index = d.month - 1 + n
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def month_range(start: date, end: date):
    """Liste des (annee, mois) de start a end inclus."""
    months = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append((y, m))
        m += 1
        if m == 13:
            m = 1
            y += 1
    return months


HIST_MONTHS = month_range(HIST_START, HIST_END)


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

@dataclass
class Client:
    nom: str
    montant_mensuel: float
    freq_par_mois: float          # 1 = mensuel, 2 = bimensuel, 0.5 = un mois sur deux
    delai_paiement_contractuel: int  # conditions de paiement (jours)
    delai_base: int                # retard "normal" moyen (jours), hors anomalie
    degradant: bool = False        # True uniquement pour le client anomalie n2

    def montant_facture(self) -> float:
        base = self.montant_mensuel / max(self.freq_par_mois, 1)
        return round(base * random.uniform(0.85, 1.15), 2)


CLIENTS = [
    Client("Meunier Negoce",        18_000, 1,   30, 6, degradant=True),   # ANOMALIE 1 : degradation du DSO
    Client("Dupont Materiaux",      22_000, 1,   30, 3),
    Client("SARL Lefevre Equipements", 15_000, 1, 45, 10),
    Client("Groupe Charpentier",    12_000, 1,   30, 5),
    Client("Bernard Fils",           9_000, 1,   30, 7),
    Client("Distri Ouest",          16_000, 1,   30, 2),
    Client("Petit & Cie",            6_000, 1,   30, 15),   # retard chronique mais STABLE (pas une anomalie)
    Client("Techno Bat",             8_000, 0.5, 30, 5),
    Client("Marchand Freres",       11_000, 1,   30, 4),
    Client("Rousseau Negoce",        7_000, 1,   30, 20),
    Client("Alpha Fournitures",      5_000, 1,   30, 6),
    Client("Nord Equipement",        9_500, 1,   30, 8),
    Client("Central Bricolage",      6_500, 2,   30, 5),
    Client("Vallee Distribution",    4_000, 1,   30, 10),
]


def delai_meunier(months_ago: int) -> int:
    """Degradation progressive du delai de paiement (ANOMALIE 1)."""
    if months_ago >= 4:
        return random.randint(2, 8)
    if months_ago == 3:
        return random.randint(10, 15)
    if months_ago == 2:
        return random.randint(20, 28)
    if months_ago == 1:
        return random.randint(32, 40)
    return random.randint(45, 55)  # mois courant : facture recente, tres en retard


# ---------------------------------------------------------------------------
# Fournisseurs
# ---------------------------------------------------------------------------

@dataclass
class Fournisseur:
    nom: str
    montant_mensuel: float
    freq_par_mois: float
    delai_paiement_contractuel: int
    delai_base: int = 2  # l'entreprise paie globalement dans les temps

    def montant_facture(self) -> float:
        base = self.montant_mensuel / max(self.freq_par_mois, 1)
        return round(base * random.uniform(0.9, 1.1), 2)


FOURNISSEURS = [
    Fournisseur("Global Import SA",         45_000, 1, 45),   # ANOMALIE 3 : reappro exceptionnel
    Fournisseur("Materiel Pro Distribution", 30_000, 1, 30),
    Fournisseur("Trans Log Express",          9_000, 1, 30),
    Fournisseur("EnerFret",                   4_500, 2, 30),
    Fournisseur("Emballages Dupuis",          2_000, 1, 30),
    Fournisseur("Outillage Services",         1_500, 0.5, 30),
]


# ---------------------------------------------------------------------------
# Charges recurrentes (connues a l'avance -> alimentent aussi la projection)
# ---------------------------------------------------------------------------

@dataclass
class ChargeRecurrente:
    libelle: str
    categorie: str
    montant: float
    frequence: str          # "mensuelle" ou "trimestrielle"
    prochaine_echeance: date
    intervalle_jours: int


CHARGES_RECURRENTES = [
    ChargeRecurrente("Loyer entrepot", "Loyer", 10_500, "trimestrielle", date(2026, 10, 8), 91),
    ChargeRecurrente("Salaires (5 ETP, charges comprises)", "Salaires", 19_000, "mensuelle", date(2026, 9, 30), 30),
    ChargeRecurrente("Emprunts (vehicules + local)", "Emprunt", 11_600, "mensuelle", date(2026, 10, 5), 30),
    ChargeRecurrente("Assurance professionnelle", "Frais generaux", 950, "mensuelle", date(2026, 10, 10), 30),
    ChargeRecurrente("Abonnements logiciels (ERP/CRM/compta)", "Abonnements", 620, "mensuelle", date(2026, 10, 5), 30),
]

# ANOMALIE 3 (partie fournisseur) : grosse commande exceptionnelle chez
# Global Import SA, echeance choisie pour tomber la meme semaine que le
# loyer trimestriel et l'echeance d'emprunt/abonnements ci-dessus
# (semaine du 4 au 10 octobre 2026).
COMMANDE_EXCEPTIONNELLE = dict(
    fournisseur="Global Import SA",
    montant=100_000.0,
    date_emission=date(2026, 8, 24),
    date_echeance=date(2026, 10, 8),
)

# ANOMALIE 2 : depense inhabituelle, hors cycle fournisseur/facture, categorie "Frais generaux"
DEPENSE_INHABITUELLE = dict(
    date=date(2026, 7, 14),
    libelle="Reparation urgente vehicule utilitaire (panne moteur)",
    montant=-4_300.0,
    categorie="Frais generaux",
)

LIBELLES_FRAIS_DIVERS = [
    "Fournitures de bureau",
    "Entretien local",
    "Petit outillage",
    "Frais divers exploitation",
    "Frais bancaires",
]


# ---------------------------------------------------------------------------
# Generation des factures clients
# ---------------------------------------------------------------------------

def generer_jours_facturation(y: int, m: int, freq: float) -> list[int]:
    max_day = calendar.monthrange(y, m)[1]
    if (y, m) == (TODAY.year, TODAY.month):
        max_day = min(max_day, HIST_END.day)
    if max_day < 1:
        return []
    if freq >= 2:
        return sorted({random.randint(1, max(1, max_day // 2)), random.randint(max_day // 2 + 1, max_day)})
    if freq == 1:
        return [random.randint(1, max_day)]
    # freq == 0.5 : un mois sur deux (mois pairs de la fenetre d'historique)
    idx = HIST_MONTHS.index((y, m))
    return [random.randint(1, max_day)] if idx % 2 == 0 else []


def generer_factures_clients():
    factures = []
    seq = 1
    for client in CLIENTS:
        for (y, m) in HIST_MONTHS:
            for jour in generer_jours_facturation(y, m, client.freq_par_mois):
                emission = date(y, m, jour)
                echeance = emission + timedelta(days=client.delai_paiement_contractuel)
                months_ago = (TODAY.year - y) * 12 + (TODAY.month - m)
                if client.degradant:
                    delai = delai_meunier(months_ago)
                else:
                    delai = max(0, client.delai_base + random.randint(-3, 4))
                paiement_projete = echeance + timedelta(days=delai)
                date_paiement = paiement_projete if paiement_projete <= HIST_END else None
                factures.append({
                    "numero": f"FC{y}{m:02d}{seq:04d}",
                    "client": client.nom,
                    "montant": client.montant_facture(),
                    "date_emission": emission,
                    "date_echeance": echeance,
                    "date_paiement": date_paiement,
                    "_paiement_projete": paiement_projete,  # usage interne (diagnostic), pas exporte
                })
                seq += 1
    return factures


def generer_factures_fournisseurs():
    factures = []
    seq = 1
    for fournisseur in FOURNISSEURS:
        for (y, m) in HIST_MONTHS:
            for jour in generer_jours_facturation(y, m, fournisseur.freq_par_mois):
                emission = date(y, m, jour)
                echeance = emission + timedelta(days=fournisseur.delai_paiement_contractuel)
                delai = max(0, fournisseur.delai_base + random.randint(-2, 3))
                paiement_projete = echeance + timedelta(days=delai)
                date_paiement = paiement_projete if paiement_projete <= HIST_END else None
                factures.append({
                    "numero": f"FF{y}{m:02d}{seq:04d}",
                    "fournisseur": fournisseur.nom,
                    "montant": fournisseur.montant_facture(),
                    "date_emission": emission,
                    "date_echeance": echeance,
                    "date_paiement": date_paiement,
                    "_paiement_projete": paiement_projete,
                })
                seq += 1

    # ANOMALIE 3 : ajout de la commande exceptionnelle (toujours ouverte, echeance future)
    factures.append({
        "numero": f"FF{COMMANDE_EXCEPTIONNELLE['date_emission'].year}{COMMANDE_EXCEPTIONNELLE['date_emission'].month:02d}9999",
        "fournisseur": COMMANDE_EXCEPTIONNELLE["fournisseur"],
        "montant": COMMANDE_EXCEPTIONNELLE["montant"],
        "date_emission": COMMANDE_EXCEPTIONNELLE["date_emission"],
        "date_echeance": COMMANDE_EXCEPTIONNELLE["date_echeance"],
        "date_paiement": None,
        "_paiement_projete": COMMANDE_EXCEPTIONNELLE["date_echeance"],
    })
    return factures


# ---------------------------------------------------------------------------
# Transactions bancaires (historique reconstitue a partir des factures payees
# + charges recurrentes echues + depenses diverses)
# ---------------------------------------------------------------------------

def occurrences_historiques(charge: ChargeRecurrente):
    """Toutes les echeances passees d'une charge recurrente, entre HIST_START et HIST_END."""
    occ = []
    d = charge.prochaine_echeance
    while d >= HIST_START:
        d = d - timedelta(days=charge.intervalle_jours)
        if HIST_START <= d <= HIST_END:
            occ.append(d)
    return occ


def generer_transactions(factures_clients, factures_fournisseurs):
    transactions = []

    for f in factures_clients:
        if f["date_paiement"] is not None:
            transactions.append({
                "date": f["date_paiement"],
                "libelle": f"Reglement facture {f['numero']} - {f['client']}",
                "montant": round(f["montant"], 2),
                "categorie": "Encaissement client",
            })

    for f in factures_fournisseurs:
        if f["date_paiement"] is not None:
            transactions.append({
                "date": f["date_paiement"],
                "libelle": f"Paiement facture {f['numero']} - {f['fournisseur']}",
                "montant": -round(f["montant"], 2),
                "categorie": "Paiement fournisseur",
            })

    for charge in CHARGES_RECURRENTES:
        for d in occurrences_historiques(charge):
            transactions.append({
                "date": d,
                "libelle": charge.libelle,
                "montant": -charge.montant,
                "categorie": charge.categorie,
            })

    # Frais generaux divers (base statistique pour la detection d'anomalie)
    for (y, m) in HIST_MONTHS:
        max_day = calendar.monthrange(y, m)[1]
        if (y, m) == (TODAY.year, TODAY.month):
            max_day = min(max_day, HIST_END.day)
        for _ in range(random.randint(3, 5)):
            if max_day < 1:
                break
            jour = random.randint(1, max_day)
            transactions.append({
                "date": date(y, m, jour),
                "libelle": random.choice(LIBELLES_FRAIS_DIVERS),
                "montant": -round(random.uniform(80, 650), 2),
                "categorie": "Frais generaux",
            })

    # ANOMALIE 2 : depense inhabituelle
    transactions.append({
        "date": DEPENSE_INHABITUELLE["date"],
        "libelle": DEPENSE_INHABITUELLE["libelle"],
        "montant": DEPENSE_INHABITUELLE["montant"],
        "categorie": DEPENSE_INHABITUELLE["categorie"],
    })

    transactions.sort(key=lambda t: t["date"])
    return transactions


# ---------------------------------------------------------------------------
# Ecriture des CSV
# ---------------------------------------------------------------------------

def ecrire_csv(path: Path, fieldnames: list[str], rows: list[dict]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def formater_facture(f: dict, cle_tiers: str) -> dict:
    return {
        "numero": f["numero"],
        cle_tiers: f[cle_tiers],
        "montant": f"{f['montant']:.2f}",
        "date_emission": f["date_emission"].isoformat(),
        "date_echeance": f["date_echeance"].isoformat(),
        "date_paiement": f["date_paiement"].isoformat() if f["date_paiement"] else "",
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    factures_clients = generer_factures_clients()
    factures_fournisseurs = generer_factures_fournisseurs()
    transactions = generer_transactions(factures_clients, factures_fournisseurs)

    net_flow = sum(t["montant"] for t in transactions)
    solde_depart = SOLDE_DEPART
    solde_actuel = round(solde_depart + net_flow, 2)

    # --- Export CSV ---
    ecrire_csv(
        OUT_DIR / "transactions_bancaires.csv",
        ["date", "libelle", "montant", "categorie"],
        [{"date": t["date"].isoformat(), "libelle": t["libelle"],
          "montant": f"{t['montant']:.2f}", "categorie": t["categorie"]} for t in transactions],
    )

    ecrire_csv(
        OUT_DIR / "factures_clients.csv",
        ["numero", "client", "montant", "date_emission", "date_echeance", "date_paiement"],
        [formater_facture(f, "client") for f in factures_clients],
    )

    ecrire_csv(
        OUT_DIR / "factures_fournisseurs.csv",
        ["numero", "fournisseur", "montant", "date_emission", "date_echeance", "date_paiement"],
        [formater_facture(f, "fournisseur") for f in factures_fournisseurs],
    )

    ecrire_csv(
        OUT_DIR / "charges_recurrentes.csv",
        ["libelle", "categorie", "montant", "frequence", "prochaine_echeance", "intervalle_jours"],
        [{
            "libelle": c.libelle, "categorie": c.categorie, "montant": f"{c.montant:.2f}",
            "frequence": c.frequence, "prochaine_echeance": c.prochaine_echeance.isoformat(),
            "intervalle_jours": c.intervalle_jours,
        } for c in CHARGES_RECURRENTES],
    )

    ecrire_csv(
        OUT_DIR / "solde_bancaire_depart.csv",
        ["date", "solde", "libelle"],
        [{"date": HIST_START.isoformat(), "solde": f"{solde_depart:.2f}",
          "libelle": f"Solde d'ouverture au {HIST_START.isoformat()}"}],
    )

    # -----------------------------------------------------------------
    # Diagnostics (QA interne, pas livre dans le workflow) :
    # verifie que les 3 anomalies sont bien detectables avant validation.
    # -----------------------------------------------------------------
    print("=" * 70)
    print("RESUME")
    print("=" * 70)
    ca_total = sum(f["montant"] for f in factures_clients)
    achats_total = sum(f["montant"] for f in factures_fournisseurs)
    print(f"CA total periode (factures emises)      : {ca_total:,.0f} EUR")
    print(f"Achats fournisseurs totaux (emis)        : {achats_total:,.0f} EUR")
    print(f"Nombre de factures clients                : {len(factures_clients)}")
    print(f"Nombre de factures fournisseurs           : {len(factures_fournisseurs)}")
    print(f"Nombre de transactions bancaires           : {len(transactions)}")
    print(f"Flux net historique (transactions)        : {net_flow:,.2f} EUR")
    print(f"Solde d'ouverture fixe ({HIST_START})      : {solde_depart:,.2f} EUR")
    print(f"Solde actuel resultant (au {TODAY})        : {solde_actuel:,.2f} EUR")

    print("\n" + "=" * 70)
    print("ANOMALIE 1 - Degradation du delai de paiement (Meunier Negoce)")
    print("=" * 70)
    meunier = [f for f in factures_clients if f["client"] == "Meunier Negoce"]
    for f in sorted(meunier, key=lambda f: f["date_emission"])[-6:]:
        delai = (f["_paiement_projete"] - f["date_echeance"]).days
        statut = f["date_paiement"].isoformat() if f["date_paiement"] else "OUVERTE / EN RETARD"
        print(f"  {f['numero']}  emise {f['date_emission']}  echeance {f['date_echeance']}  "
              f"delai {delai:+3d}j  paiement: {statut}")

    print("\n" + "=" * 70)
    print("ANOMALIE 2 - Depense inhabituelle (categorie Frais generaux)")
    print("=" * 70)
    frais = [t["montant"] for t in transactions
             if t["categorie"] == "Frais generaux" and t["montant"] != DEPENSE_INHABITUELLE["montant"]]
    moyenne = statistics.mean(frais)
    ecart_type = statistics.stdev(frais)
    seuil = moyenne - 2 * ecart_type  # depenses = montants negatifs
    depense = DEPENSE_INHABITUELLE["montant"]
    print(f"  Moyenne categorie (hors anomalie)  : {moyenne:,.2f} EUR")
    print(f"  Ecart-type categorie                : {ecart_type:,.2f} EUR")
    print(f"  Seuil (moyenne - 2 sigma)            : {seuil:,.2f} EUR")
    print(f"  Depense injectee                    : {depense:,.2f} EUR")
    print(f"  -> Anomalie detectable : {depense < seuil}")

    print("\n" + "=" * 70)
    print("ANOMALIE 3 - Projection simplifiee de tresorerie sur 13 semaines (QA)")
    print("=" * 70)
    print("  (simulation interne au script, pas le calcul definitif du noeud Code)")

    def occurrences_futures(charge: ChargeRecurrente):
        occ = []
        d = charge.prochaine_echeance
        while d <= FORECAST_END:
            occ.append(d)
            d = d + timedelta(days=charge.intervalle_jours)
        return occ

    flux_futurs = []
    for f in factures_clients:
        if f["date_paiement"] is None and TODAY <= f["_paiement_projete"] <= FORECAST_END:
            flux_futurs.append((f["_paiement_projete"], f["montant"]))
    for f in factures_fournisseurs:
        if f["date_paiement"] is None and TODAY <= f["_paiement_projete"] <= FORECAST_END:
            flux_futurs.append((f["_paiement_projete"], -f["montant"]))
    for charge in CHARGES_RECURRENTES:
        for d in occurrences_futures(charge):
            flux_futurs.append((d, -charge.montant))

    solde = solde_actuel
    seuil_alerte = 15_000.0
    semaine_debut = TODAY
    alertes = []
    for s in range(FORECAST_WEEKS):
        semaine_fin = semaine_debut + timedelta(days=7)
        flux_semaine = sum(m for d, m in flux_futurs if semaine_debut <= d < semaine_fin)
        solde += flux_semaine
        marqueur = "  <-- SOUS SEUIL" if solde < seuil_alerte else ""
        print(f"  Semaine {s+1:2d} ({semaine_debut} -> {semaine_fin - timedelta(days=1)}) : "
              f"flux net {flux_semaine:+10,.0f} EUR   solde projete {solde:10,.0f} EUR{marqueur}")
        if solde < seuil_alerte:
            alertes.append(s + 1)
        semaine_debut = semaine_fin

    print(f"\n  -> Semaine(s) sous le seuil d'alerte ({seuil_alerte:,.0f} EUR) : {alertes or 'aucune'}")
    print("\nFichiers ecrits dans:", OUT_DIR.resolve())


if __name__ == "__main__":
    main()
