"""
Configuration pour le bot Barco ICMP
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration Barco - URLs des salles
BARCO_URL_SALLE2 = os.getenv("BARCO_URL_SALLE2", "https://10.66.80.192:43744")
BARCO_URL_SALLE3 = os.getenv("BARCO_URL_SALLE3", "https://10.66.80.193:43744")

# URL par défaut
BARCO_URL = os.getenv("BARCO_URL", BARCO_URL_SALLE3)

# Dictionnaire des salles
SALLES = {
    2: BARCO_URL_SALLE2,
    3: BARCO_URL_SALLE3,
    "salle2": BARCO_URL_SALLE2,
    "salle3": BARCO_URL_SALLE3,
}

BARCO_USERNAME = os.getenv("BARCO_USERNAME", "admin")
BARCO_PASSWORD = os.getenv("BARCO_PASSWORD", "Admin123")

# Chemin vers les fichiers QFC
QFC_FOLDER_PATH = os.getenv("QFC_FOLDER_PATH", r"C:\Films\QFC")

# Volume par défaut
DEFAULT_VOLUME = int(os.getenv("DEFAULT_VOLUME", "51"))

# Format par défaut (scope ou flat)
DEFAULT_FORMAT = os.getenv("DEFAULT_FORMAT", "scope")

# Formats disponibles
FORMATS = {
    "scope": "2.39:1",
    "flat": "1.85:1"
}
