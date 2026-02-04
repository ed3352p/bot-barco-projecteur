"""
Bot Barco ICMP - Menu Principal
Demande quelle salle au démarrage
"""
from datetime import datetime, timedelta
from barco_bot import BarcoBot
from config import SALLES


def afficher_menu():
    """Affiche le menu de sélection de salle"""
    print("\n" + "="*50)
    print("       BOT BARCO ICMP - AUTOMATISATION")
    print("="*50)
    print("\nSélectionnez la salle:")
    print("  [2] Salle 2 - 10.66.80.192")
    print("  [3] Salle 3 - 10.66.80.193")
    print("  [q] Quitter")
    print("-"*50)


def demander_salle():
    """Demande à l'utilisateur de choisir une salle"""
    while True:
        afficher_menu()
        choix = input("Votre choix: ").strip().lower()
        
        if choix == "2":
            return 2
        elif choix == "3":
            return 3
        elif choix == "q":
            return None
        else:
            print("[ERREUR] Choix invalide. Entrez 2, 3 ou q")


def get_salle_name(salle):
    """Retourne le nom de la salle pour le bloc"""
    if salle == 2:
        return "Selectotel"
    elif salle == 3:
        return "Brunet"
    return "Brunet"


def demander_minutes():
    """Demande les minutes de la séance (00, 15 ou 30)"""
    print("\nMinutes de la séance:")
    print("  [0] :00 -> start 18h50 / 12h50")
    print("  [1] :15 -> start 19h05 / 13h05")
    print("  [2] :30 -> start 19h20 / 13h20")
    
    while True:
        choix = input("Votre choix (0/1/2): ").strip()
        if choix == "0":
            return "00"
        elif choix == "1":
            return "15"
        elif choix == "2":
            return "30"
        else:
            print("[ERREUR] Choix invalide. Entrez 0, 1 ou 2")


def demander_date_debut():
    """
    Demande la date de début (vendredi) pour programmer les séances
    La plage est automatiquement de 7 jours (vendredi -> jeudi)
    
    Returns:
        str: Date de début au format "DD/MM/YYYY"
    """
    print("\n" + "="*50)
    print("       DATE DE DÉBUT DU SCHEDULING")
    print("="*50)
    
    # Calculer le vendredi prochain par défaut
    today = datetime.now()
    days_until_friday = (4 - today.weekday()) % 7
    if days_until_friday == 0 and today.hour >= 12:  # Si on est vendredi après-midi
        days_until_friday = 7
    vendredi_prochain = today + timedelta(days=days_until_friday)
    
    date_debut_defaut = vendredi_prochain.strftime("%d/%m/%Y")
    
    print(f"\nDate de début (vendredi) [défaut: {date_debut_defaut}]:")
    print("  Format: JJ/MM/AAAA (ex: 07/02/2026)")
    print("  Appuyez sur Entrée pour utiliser la date par défaut")
    print("\n  Jours programmés:")
    print("    - Ven/Sam/Dim/Mer/Jeu: soir + après-midi (sam/dim)")
    print("    - Lun/Mar: rien")
    
    while True:
        date_debut_input = input("\nDate de début: ").strip()
        
        if date_debut_input == "":
            date_debut = date_debut_defaut
            break
        
        # Valider le format
        try:
            datetime.strptime(date_debut_input, "%d/%m/%Y")
            date_debut = date_debut_input
            break
        except ValueError:
            print("[ERREUR] Format invalide. Utilisez JJ/MM/AAAA")
    
    # Calculer la date de fin (jeudi = +6 jours)
    date_debut_dt = datetime.strptime(date_debut, "%d/%m/%Y")
    date_fin_dt = date_debut_dt + timedelta(days=6)
    date_fin = date_fin_dt.strftime("%d/%m/%Y")
    
    print(f"\n[INFO] Plage: {date_debut} (ven) -> {date_fin} (jeu)")
    return date_debut, date_fin


def main():
    """Fonction principale avec menu interactif"""
    print("\n" + "="*50)
    print("       BOT BARCO ICMP - AUTOMATISATION")
    print("="*50)
    
    # Demander la salle
    salle = demander_salle()
    
    if salle is None:
        print("\n[INFO] Au revoir!")
        return
    
    print(f"\n[INFO] Salle {salle} sélectionnée")
    
    # Demander les minutes de la séance
    minutes = demander_minutes()
    
    # Demander la date de début (7 jours automatiques)
    date_debut, date_fin = demander_date_debut()
    
    # Le nom du bloc sera auto-généré: Salle - F/S - NomFilm
    salle_name = get_salle_name(salle)
    print(f"\n[INFO] Le nom du bloc sera auto-généré: {salle_name} - F/S - <nom du film>")
    
    # Créer le bot pour la salle choisie
    bot = BarcoBot(headless=False, salle=salle)
    
    # Passer le nom de la salle au bot pour la génération du nom du bloc
    bot.salle_name = salle_name
    
    print("\n" + "="*50)
    print("       DÉMARRAGE DU WORKFLOW")
    print("="*50)
    print(f"  Salle: {salle} ({salle_name})")
    print(f"  Bloc: AUTO (nom extrait du film importé)")
    print(f"  Minutes: :{minutes}")
    print(f"  Plage: {date_debut} -> {date_fin}")
    print(f"  Volume: 51")
    print("="*50 + "\n")
    
    # Lancer le workflow complet - tout est automatique
    bot.full_workflow_usb(
        film_name=None,       # Prend le premier QFC (ou FR si pas de QFC)
        block_name=None,      # Auto-généré depuis le nom du film
        minutes=minutes,      # Minutes de la séance
        date_debut=date_debut,  # Date de début du scheduling
        date_fin=date_fin       # Date de fin du scheduling
    )
    
    print("\n[INFO] Workflow terminé!")
    
    # Demander si on veut faire une autre salle
    autre = input("\nFaire une autre salle? (o/n): ").strip().lower()
    if autre == "o":
        main()


if __name__ == "__main__":
    main()
