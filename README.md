# Bot Barco ICMP - Automatisation Projecteur

Bot Selenium pour automatiser les opérations sur projecteur **Barco ICMP**.

## Fonctionnalités

- **Import USB** de films (QFC prioritaire, FR en fallback)
- **Détection automatique** du format (Scope/Flat)
- **Sélection automatique** du bloc selon le format
- **Renommage automatique** du bloc: `Salle - F/S - NomFilm`
- **Scheduling** des séances sur 7 jours (Ven→Jeu)

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Copier `.env.example` vers `.env`:

```env
BARCO_URL_SALLE2=https://10.66.80.192:43744
BARCO_URL_SALLE3=https://10.66.80.193:43744
BARCO_USERNAME=admin
BARCO_PASSWORD=Admin123
```

## Utilisation

### Lancement

```bash
python main.py
```

Ou double-cliquer sur `start_bot.bat`

### Menu

```
Sélectionnez la salle:
  [2] Salle 2 (Selectotel)
  [3] Salle 3 (Brunet)

Minutes de la séance:
  [0] :00 -> start 18h50 / 12h50
  [1] :15 -> start 19h05 / 13h05
  [2] :30 -> start 19h20 / 13h20
```

### Workflow automatique

1. **Login** sur l'interface Barco
2. **Import USB** - Sélectionne QFC (ou FR) avec volume 51
3. **Éditeur de séance** - Sélectionne le bloc selon format (-s- ou -f-)
4. **Remplacement film** + renommage automatique
5. **Scheduling** - Programme Ven/Sam/Dim/Mer/Jeu

## Horaires programmés

| Minutes | Soir | Après-midi (Sam/Dim) |
|---------|------|---------------------|
| :00 | 18h50 | 12h50 |
| :15 | 19h05 | 13h05 |
| :30 | 19h20 | 13h20 |

## Structure

```
bot-barco/
├── main.py           # Point d'entrée (menu interactif)
├── barco_bot.py      # Bot Selenium
├── config.py         # Configuration
├── start_bot.bat     # Lanceur Windows
├── requirements.txt  # Dépendances
└── .env.example      # Config exemple
```

## Notes

- Chrome requis (Selenium 4 gère ChromeDriver automatiquement)
- Les séances sont ajoutées avec "Fermer lampe" automatiquement
