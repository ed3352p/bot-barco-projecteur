"""
Bot Selenium pour projecteur Barco ICMP
- Import de films en QFC via USB
- Configuration volume à 51
- Création de blocs avec format Scope ou Flat
- Scheduling des projections
"""
import os
import time
import glob
import logging
import traceback
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import (
    WebDriverException,
    NoSuchElementException,
    TimeoutException,
    ElementClickInterceptedException,
    ElementNotInteractableException,
    StaleElementReferenceException
)
from webdriver_manager.chrome import ChromeDriverManager

from config import (
    BARCO_URL, BARCO_USERNAME, BARCO_PASSWORD,
    QFC_FOLDER_PATH, DEFAULT_VOLUME, DEFAULT_FORMAT, FORMATS,
    SALLES, BARCO_URL_SALLE2, BARCO_URL_SALLE3
)

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('barco_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class BarcoBot:
    """Bot pour automatiser les opérations sur projecteur Barco ICMP"""
    
    def __init__(self, headless=False, salle=None):
        """
        Initialise le bot Selenium avec gestion des erreurs améliorée
        
        Args:
            headless: Si True, exécute le navigateur en mode headless
            salle: Numéro de salle (2 ou 3) ou None pour utiliser l'URL par défaut
            
        Raises:
            WebDriverException: Si l'initialisation du WebDriver échoue
            Exception: Pour toute autre erreur inattendue
        """
        try:
            self.driver = None
            self.headless = headless
            self.wait = None
            self.wait_long = None
            self.max_retries = 3
            self.retry_delay = 2
            
            # Vérification des paramètres
            if not isinstance(headless, bool):
                logger.warning("Le paramètre 'headless' doit être un booléen. Utilisation de la valeur par défaut (False).")
                self.headless = False
            
            # Sélectionner l'URL de la salle
            if salle is not None:
                if salle not in SALLES:
                    logger.warning(f"Salle {salle} non trouvée. Utilisation de l'URL par défaut.")
                self.barco_url = SALLES.get(salle, BARCO_URL)
                self.salle = salle
            else:
                self.barco_url = BARCO_URL
                self.salle = None
                
            logger.info(f"Initialisation du bot pour la salle: {self.salle or 'par défaut'}")
            # Le navigateur sera démarré par start_browser() dans full_workflow_usb()
            
        except Exception as e:
            logger.error(f"Erreur inattendue lors de l'initialisation: {str(e)}")
            raise
        
    def start_browser(self):
        """Démarre le navigateur Chrome"""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--ignore-certificate-errors")  # Pour HTTPS auto-signé
        
        # Utiliser Selenium 4 avec gestionnaire automatique (sans webdriver-manager)
        self.driver = webdriver.Chrome(options=chrome_options)
        self.wait = WebDriverWait(self.driver, 20)
        self.wait_long = WebDriverWait(self.driver, 60)
        salle_info = f" pour Salle {self.salle}" if self.salle else ""
        print(f"[INFO] Navigateur démarré{salle_info}")
        
    def close_browser(self):
        """Ferme le navigateur"""
        if self.driver:
            self.driver.quit()
            print("[INFO] Navigateur fermé")
    
    def wait_for_page_load(self):
        """Attend que la page soit complètement chargée"""
        time.sleep(2)
        self.wait.until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
            
    def login(self):
        """Se connecte à l'interface web Barco ICMP"""
        try:
            salle_info = f" (Salle {self.salle})" if self.salle else ""
            self.driver.get(self.barco_url)
            print(f"[INFO] Connexion à {self.barco_url}{salle_info}")
            
            self.wait_for_page_load()
            
            # Attendre le champ username - Barco ICMP utilise différents sélecteurs possibles
            username_field = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 
                    "input[name='username'], input[id='username'], input[type='text'][placeholder*='user' i], input.username"))
            )
            username_field.clear()
            username_field.send_keys(BARCO_USERNAME)
            
            # Remplir le mot de passe
            password_field = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR,
                    "input[name='password'], input[id='password'], input[type='password']"))
            )
            password_field.clear()
            password_field.send_keys(BARCO_PASSWORD)
            
            # Cliquer sur le bouton de connexion
            login_button = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR,
                    "button[type='submit'], input[type='submit'], button.login, .btn-login, #loginButton, button[id*='login' i]"))
            )
            login_button.click()
            
            # Attendre que la page principale se charge (content wrapper de Barco ICMP)
            self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#content, #contentWrapper, .container, #header"))
            )
            
            self.wait_for_page_load()
            print("[INFO] Connexion réussie")
            return True
            
        except Exception as e:
            print(f"[ERREUR] Échec de connexion: {e}")
            return False
    
    def navigate_to_import_usb(self):
        """Navigue vers Import USB pour importer les films QFC"""
        try:
            # Étape 1: Navigation vers /#sms/ingest
            ingest_url = f"{self.barco_url}/#sms/ingest"
            print(f"[INFO] Étape 1: Navigation vers {ingest_url}")
            self.driver.get(ingest_url)
            
            self.wait_for_page_load()
            time.sleep(3)
            
            # Étape 2: Cliquer sur l'onglet Storage View
            print("[INFO] Étape 2: Clic sur l'onglet Storage View...")
            storage_tab = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 
                    "a[href='#tabs-storageview'], a[href*='storageview'], #tabs-storageview, [data-toggle='tab'][href*='storage']"))
            )
            storage_tab.click()
            
            self.wait_for_page_load()
            time.sleep(2)
            
            # Étape 3: Sélectionner USB dans le menu déroulant #selectSourceIngest
            print("[INFO] Étape 3: Sélection de USB dans le menu déroulant...")
            select_element = self.wait.until(
                EC.presence_of_element_located((By.ID, "selectSourceIngest"))
            )
            
            # Utiliser Select pour le menu déroulant
            select = Select(select_element)
            select.select_by_value("usb")
            
            self.wait_for_page_load()
            time.sleep(2)
            
            print("[INFO] USB sélectionné - Prêt pour importer")
            return True
            
        except Exception as e:
            print(f"[ERREUR] Navigation Import USB: {e}")
            return False
            
    def navigate_to_content_manager(self):
        """Navigue vers le gestionnaire de contenu"""
        try:
            content_menu = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, 
                    "//a[contains(text(), 'Content') or contains(text(), 'Contenu')]"
                    " | //div[contains(text(), 'Content')]"
                    " | //*[@data-tr='CONTENT']"))
            )
            content_menu.click()
            time.sleep(1)
            
            content_manager = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, 
                    "//a[contains(text(), 'Content Manager') or contains(text(), 'Gestionnaire') or contains(text(), 'Manager')]"
                    " | //*[@data-tr='CONTENT_MANAGER']"))
            )
            content_manager.click()
            
            self.wait_for_page_load()
            print("[INFO] Navigation vers Content Manager")
            return True
        except Exception as e:
            print(f"[ERREUR] Navigation Content Manager: {e}")
            return False
            
    def apply_filter_newest_to_oldest(self):
        """
        Applique le filtre 'Nouveaux à anciens' (tri par date décroissante)
        """
        try:
            print("[INFO] Application du filtre: Nouveaux à anciens...")
            
            # Chercher le bouton/dropdown de tri
            sort_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH,
                    "//select[contains(@id, 'sort') or contains(@name, 'sort') or contains(@class, 'sort')]"
                    " | //button[contains(text(), 'Sort') or contains(text(), 'Tri') or contains(text(), 'Filter')]"
                    " | //*[contains(@class, 'sort') or contains(@class, 'filter')]"
                    " | //*[@data-tr='SORT'] | //*[@data-tr='FILTER']"
                    " | //div[contains(@class, 'dropdown') and contains(., 'Sort')]"
                    " | //a[contains(text(), 'Date') or contains(@class, 'sort-date')]"))
            )
            sort_button.click()
            time.sleep(1)
            
            # Sélectionner l'option "Nouveaux à anciens" / "Newest to oldest" / "Date desc"
            newest_option = self.wait.until(
                EC.element_to_be_clickable((By.XPATH,
                    "//*[contains(text(), 'Nouveaux') or contains(text(), 'Newest') or contains(text(), 'Recent')]"
                    " | //*[contains(text(), 'nouveau') or contains(text(), 'newest') or contains(text(), 'recent')]"
                    " | //option[contains(text(), 'Date') and (contains(text(), 'desc') or contains(text(), 'Desc'))]"
                    " | //*[contains(text(), 'Date ↓') or contains(text(), 'Date (desc)')]"
                    " | //li[contains(text(), 'Nouveaux') or contains(text(), 'Newest')]"
                    " | //a[contains(text(), 'Nouveaux') or contains(text(), 'Newest')]"))
            )
            newest_option.click()
            
            self.wait_for_page_load()
            print("[INFO] Filtre 'Nouveaux à anciens' appliqué")
            return True
            
        except Exception as e:
            print(f"[INFO] Filtre non trouvé ou déjà appliqué: {e}")
            return False
    
    def detect_film_format(self, film_text):
        """
        Détecte le format du film (scope ou flat) à partir du nom
        
        Args:
            film_text: Texte/nom du film
            
        Returns:
            str: 'scope' ou 'flat'
        """
        text_upper = film_text.upper()
        # Scope: contient SCOPE ou S dans le nom de format
        if 'SCOPE' in text_upper or '_S_' in text_upper or '-S-' in text_upper:
            return 'scope'
        # Flat: contient FLAT ou F dans le nom de format
        if 'FLAT' in text_upper or '_F_' in text_upper or '-F-' in text_upper:
            return 'flat'
        # Par défaut scope
        return 'scope'
    
    def extract_film_name(self, qfc_text):
        """
        Extrait le nom du film depuis le nom complet du fichier QFC
        Exemple: "Mercy_TLR-1-IMMINA_S_QFC-QFC-CCAP_CA_51_4K_MGM_20251001_DLX_SMPTE_OV" -> "Mercy"
        
        Args:
            qfc_text: Texte complet du nom QFC
            
        Returns:
            str: Nom du film extrait (juste le titre, ex: "Mercy")
        """
        import re
        
        # Nettoyer le texte
        text = qfc_text.strip()
        
        # Prendre la première ligne si plusieurs lignes
        if '\n' in text:
            text = text.split('\n')[0]
        
        # Méthode 1: Extraire le premier mot/segment avant les codes techniques
        # Format typique: NomFilm_TLR... ou NomFilm-TLR... ou NomFilm_QFC...
        
        # Chercher le pattern: début du nom jusqu'au premier code technique
        # Codes techniques communs: TLR, FTR, TSR, QFC, DCP, SMPTE, etc.
        match = re.match(r'^([A-Za-z0-9]+)', text)
        if match:
            film_name = match.group(1)
            
            # Si le nom est trop court (moins de 3 caractères), essayer autrement
            if len(film_name) >= 3:
                # Capitaliser proprement
                return film_name.title()
        
        # Méthode 2: Prendre tout avant le premier underscore ou tiret suivi de codes
        patterns_stop = [
            r'[_-]TLR.*$',        # Trailer
            r'[_-]FTR.*$',        # Feature
            r'[_-]TSR.*$',        # Teaser
            r'[_-]QFC.*$',        # QFC
            r'[_-]DCP.*$',        # DCP
            r'[_-]\d+[_-].*$',    # Numéro suivi de codes
            r'[_-][SF][_-].*$',   # Format S ou F
            r'[_-]SMPTE.*$',      # SMPTE
            r'[_-]CCAP.*$',       # CCAP
            r'[_-]OCAP.*$',       # OCAP
            r'[_-]OV$',           # OV à la fin
            r'[_-]\d{8}.*$',      # Date 8 chiffres
            r'[_-]\d+K.*$',       # Résolution (2K, 4K)
        ]
        
        film_name = text
        for pattern in patterns_stop:
            film_name = re.sub(pattern, '', film_name, flags=re.IGNORECASE)
        
        # Prendre juste le premier segment (avant _ ou -)
        first_segment = re.split(r'[_-]', film_name)[0]
        
        if first_segment and len(first_segment) >= 2:
            return first_segment.title()
        
        # Fallback: retourner le nom nettoyé
        film_name = film_name.replace('_', ' ').replace('-', ' ').strip()
        if film_name:
            # Prendre juste le premier mot
            first_word = film_name.split()[0] if film_name.split() else film_name
            return first_word.title()
        
        return "Film"
    
    def generate_block_name(self, film_name, format_type, salle="Brunet"):
        """
        Génère le nom du bloc au format: Salle - F/S - NomFilm
        Exemple: "Brunet - F - norvege"
        
        Args:
            film_name: Nom du film
            format_type: 'scope' ou 'flat'
            salle: Nom de la salle (par défaut "Brunet")
            
        Returns:
            str: Nom du bloc formaté
        """
        format_letter = "S" if format_type.lower() == "scope" else "F"
        return f"{salle} - {format_letter} - {film_name}"
    
    def select_qfc_from_usb(self, film_name=None):
        """
        Sélectionne un film QFC depuis la liste USB dans l'interface Barco ICMP
        Priorité: QFC avec volume 51 d'abord, sinon FR avec volume 51
        Stocke le format détecté (scope/flat) dans self.imported_film_format
        Stocke le texte complet du film dans self.imported_film_text
        
        Args:
            film_name: Nom du film à sélectionner (si None, sélectionne le premier disponible)
            
        Returns:
            bool: True si succès, False sinon
            Le format est stocké dans self.imported_film_format
            Le texte complet est stocké dans self.imported_film_text
        """
        self.imported_film_format = None  # Reset
        self.imported_film_text = None    # Reset
        
        try:
            self.wait_for_page_load()
            
            # Attendre que la liste des fichiers USB soit chargée
            time.sleep(3)
            
            # Récupérer tous les éléments de la liste
            print("[INFO] Recherche des films disponibles...")
            
            # Chercher les fichiers dans la liste
            if film_name:
                # Sélectionner un film spécifique
                qfc_item = self.wait.until(
                    EC.element_to_be_clickable((By.XPATH,
                        f"//*[contains(text(), '{film_name}')]"
                        f" | //tr[contains(., '{film_name}')]"
                        f" | //div[contains(@class, 'item') and contains(., '{film_name}')]"
                        f" | //li[contains(., '{film_name}')]"))
                )
                qfc_item.click()
                self.imported_film_format = self.detect_film_format(film_name)
                print(f"[INFO] Film '{film_name}' sélectionné (format: {self.imported_film_format})")
                return True
            else:
                # Attendre que la liste soit chargée
                time.sleep(3)
                
                # Les films sont dans des div.rowItem dans #scanContent
                all_items = self.driver.find_elements(By.CSS_SELECTOR, "#scanContent div.rowItem")
                print(f"[INFO] {len(all_items)} films trouvés dans la liste")
                
                # Critères de sélection (avec fallback):
                # - QFC ou FR (priorité QFC)
                # - CCAP préféré (pas OCAP), mais optionnel
                # - Volume 51 ou 71 préféré, mais optionnel
                
                def has_volume(text):
                    """Vérifie si le film a volume 51 ou 71"""
                    return '_51_' in text or '-51-' in text or '_51-' in text or '-51_' in text or \
                           '_71_' in text or '-71-' in text or '_71-' in text or '-71_' in text
                
                def has_ccap_not_ocap(text):
                    """Vérifie CCAP sans OCAP"""
                    return 'CCAP' in text and 'OCAP' not in text
                
                def is_qfc(text):
                    return 'QFC' in text
                
                def is_fr(text):
                    return '_FR' in text or '-FR' in text or 'FR-' in text or '_FR_' in text
                
                # Priorité 1: QFC + CCAP + 51/71
                print("[INFO] Recherche: QFC + CCAP + 51/71...")
                for item in all_items:
                    try:
                        text = item.text.upper()
                        if is_qfc(text) and has_ccap_not_ocap(text) and has_volume(text):
                            ingest_btn = item.find_element(By.CSS_SELECTOR, "div.btnIngest")
                            ingest_btn.click()
                            self.imported_film_text = item.text
                            self.imported_film_format = self.detect_film_format(item.text)
                            print(f"[INFO] Film QFC+CCAP+51/71 importé: {item.text[:80]}... (format: {self.imported_film_format})")
                            return True
                    except:
                        continue
                
                # Priorité 2: FR + CCAP + 51/71
                print("[INFO] Recherche: FR + CCAP + 51/71...")
                for item in all_items:
                    try:
                        text = item.text.upper()
                        if is_fr(text) and has_ccap_not_ocap(text) and has_volume(text):
                            ingest_btn = item.find_element(By.CSS_SELECTOR, "div.btnIngest")
                            ingest_btn.click()
                            self.imported_film_text = item.text
                            self.imported_film_format = self.detect_film_format(item.text)
                            print(f"[INFO] Film FR+CCAP+51/71 importé: {item.text[:80]}... (format: {self.imported_film_format})")
                            return True
                    except:
                        continue
                
                # Priorité 3: QFC + 51/71 (sans CCAP)
                print("[INFO] Recherche: QFC + 51/71...")
                for item in all_items:
                    try:
                        text = item.text.upper()
                        if is_qfc(text) and has_volume(text):
                            ingest_btn = item.find_element(By.CSS_SELECTOR, "div.btnIngest")
                            ingest_btn.click()
                            self.imported_film_text = item.text
                            self.imported_film_format = self.detect_film_format(item.text)
                            print(f"[INFO] Film QFC+51/71 importé: {item.text[:80]}... (format: {self.imported_film_format})")
                            return True
                    except:
                        continue
                
                # Priorité 4: FR + 51/71 (sans CCAP)
                print("[INFO] Recherche: FR + 51/71...")
                for item in all_items:
                    try:
                        text = item.text.upper()
                        if is_fr(text) and has_volume(text):
                            ingest_btn = item.find_element(By.CSS_SELECTOR, "div.btnIngest")
                            ingest_btn.click()
                            self.imported_film_text = item.text
                            self.imported_film_format = self.detect_film_format(item.text)
                            print(f"[INFO] Film FR+51/71 importé: {item.text[:80]}... (format: {self.imported_film_format})")
                            return True
                    except:
                        continue
                
                # Priorité 5: QFC seul (sans volume)
                print("[INFO] Recherche: QFC (sans critère volume)...")
                for item in all_items:
                    try:
                        text = item.text.upper()
                        if is_qfc(text):
                            ingest_btn = item.find_element(By.CSS_SELECTOR, "div.btnIngest")
                            ingest_btn.click()
                            self.imported_film_text = item.text
                            self.imported_film_format = self.detect_film_format(item.text)
                            print(f"[INFO] Film QFC importé: {item.text[:80]}... (format: {self.imported_film_format})")
                            return True
                    except:
                        continue
                
                # Priorité 6: FR seul (sans volume)
                print("[INFO] Recherche: FR (sans critère volume)...")
                for item in all_items:
                    try:
                        text = item.text.upper()
                        if is_fr(text):
                            ingest_btn = item.find_element(By.CSS_SELECTOR, "div.btnIngest")
                            ingest_btn.click()
                            self.imported_film_text = item.text
                            self.imported_film_format = self.detect_film_format(item.text)
                            print(f"[INFO] Film FR importé: {item.text[:80]}... (format: {self.imported_film_format})")
                            return True
                    except:
                        continue
                
                print("[ERREUR] Aucun fichier QFC ou FR trouvé")
                return False
            
        except Exception as e:
            print(f"[ERREUR] Sélection film: {e}")
            return False
    
    def import_selected_qfc(self):
        """Importe le film QFC sélectionné depuis USB en cliquant sur l'icône ingest"""
        try:
            # Cliquer sur l'image ingest.png pour importer
            print("[INFO] Clic sur l'icône d'import...")
            import_icon = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR,
                    "img[src*='ingest.png'], img[src*='ingest'], .ingest-icon, .import-icon"))
            )
            import_icon.click()
            
            time.sleep(2)
            
            # Confirmer l'import si une popup apparaît
            try:
                confirm_button = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH,
                        "//button[contains(text(), 'OK') or contains(text(), 'Confirm') or contains(text(), 'Yes') or contains(text(), 'Oui')]"
                        " | //*[contains(@class, 'btn-primary')]"))
                )
                confirm_button.click()
            except:
                pass  # Pas de popup de confirmation
            
            print("[INFO] Import lancé avec succès")
            return True
            
        except Exception as e:
            print(f"[ERREUR] Import QFC: {e}")
            return False
            
    def import_qfc_from_usb(self, film_name=None):
        """
        Workflow complet: navigue vers Import USB et importe un film QFC
        L'import se fait directement en cliquant sur btnIngest dans select_qfc_from_usb
        
        Args:
            film_name: Nom du film à importer (optionnel)
        """
        if not self.navigate_to_import_usb():
            return False
            
        # select_qfc_from_usb clique directement sur btnIngest pour importer
        if not self.select_qfc_from_usb(film_name):
            return False
        
        print("[INFO] Import lancé avec succès")
        time.sleep(2)
        return True
    
    def check_import_status(self):
        """
        Vérifie le statut de l'importation dans la section Importation
        Attend que l'import soit terminé
        """
        try:
            print("[INFO] Vérification du statut d'importation...")
            
            # Naviguer vers la section Importation/Ingest status
            import_status_menu = self.wait.until(
                EC.element_to_be_clickable((By.XPATH,
                    "//a[contains(text(), 'Importation') or contains(text(), 'Import') or contains(text(), 'Ingest')]"
                    " | //div[contains(text(), 'Importation') or contains(text(), 'Import Status')]"
                    " | //*[@data-tr='IMPORTATION'] | //*[@data-tr='INGEST_STATUS'] | //*[@data-tr='IMPORT_STATUS']"
                    " | //*[contains(@class, 'import') and contains(@class, 'status')]"))
            )
            import_status_menu.click()
            
            self.wait_for_page_load()
            
            # Attendre que l'import soit terminé (100% ou Complete)
            print("[INFO] Attente de la fin de l'importation...")
            max_wait = 300  # 5 minutes max
            start_time = time.time()
            
            while time.time() - start_time < max_wait:
                try:
                    # Vérifier si l'import est terminé
                    complete_indicator = self.driver.find_elements(By.XPATH,
                        "//*[contains(text(), '100%') or contains(text(), 'Complete') or contains(text(), 'Terminé') or contains(text(), 'Done')]"
                        " | //*[contains(@class, 'complete') or contains(@class, 'success') or contains(@class, 'done')]"
                        " | //div[contains(@class, 'progress') and contains(@style, '100')]"
                    )
                    
                    if complete_indicator:
                        print("[INFO] Importation terminée!")
                        return True
                        
                    # Vérifier s'il y a une erreur
                    error_indicator = self.driver.find_elements(By.XPATH,
                        "//*[contains(@class, 'error') or contains(@class, 'failed')]"
                        " | //*[contains(text(), 'Error') or contains(text(), 'Failed') or contains(text(), 'Erreur')]"
                    )
                    
                    if error_indicator:
                        print("[ERREUR] L'importation a échoué")
                        return False
                        
                except:
                    pass
                    
                time.sleep(5)  # Vérifier toutes les 5 secondes
                
            print("[ERREUR] Timeout - L'importation n'est pas terminée")
            return False
            
        except Exception as e:
            print(f"[ERREUR] Vérification statut import: {e}")
            return False
    
    def navigate_to_session_editor(self):
        """
        Navigue vers l'Éditeur de séance (/#sms/showeditor)
        """
        try:
            print("[INFO] Navigation vers Éditeur de séance...")
            
            # Navigation directe vers /#sms/showeditor
            showeditor_url = f"{self.barco_url}/#sms/showeditor"
            print(f"[INFO] Navigation vers {showeditor_url}")
            self.driver.get(showeditor_url)
            
            self.wait_for_page_load()
            time.sleep(3)
            
            # Sélectionner "Date de création (nouveau-ancien)" dans le menu déroulant
            print("[INFO] Sélection du tri: Date de création (nouveau-ancien)...")
            try:
                # Attendre que le dropdown soit visible
                sort_dropdown = self.wait_long.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "select.dropdownSort"))
                )
                select = Select(sort_dropdown)
                # Sélectionner l'option avec data-tr="CREATION_NEWOLD" (index 3)
                select.select_by_index(3)
                print("[INFO] Tri sélectionné: Date de création (nouveau-ancien)")
            except Exception as e:
                print(f"[INFO] Tri déjà appliqué ou non trouvé: {e}")
            
            self.wait_for_page_load()
            time.sleep(2)
            
            print("[INFO] Navigation vers Éditeur de séance réussie")
            return True
            
        except Exception as e:
            print(f"[ERREUR] Navigation Éditeur de séance: {e}")
            return False
    
    def select_block(self, block_number=None, format_type=None, max_blocks=10):
        """
        Sélectionne un bloc dans l'éditeur de séance selon le format du film
        - Si format_type='scope': cherche un bloc avec '-s-' ou '- s -' dans le nom
        - Si format_type='flat': cherche un bloc avec '-f-' ou '- f -' dans le nom
        - Si aucun bloc avec le format n'est trouvé, NE MODIFIE RIEN et retourne False
        Les blocs sont dans #editorShowListContainer div.rowItem (max 10 premiers)
        
        Args:
            block_number: Numéro du bloc à sélectionner (ignoré, on utilise toujours format_type)
            format_type: 'scope' ou 'flat' pour sélectionner par format
            max_blocks: Nombre maximum de blocs à parcourir (par défaut 10)
            
        Returns:
            bool: True si un bloc avec le format a été trouvé et ouvert, False sinon
        """
        try:
            self.wait_for_page_load()
            time.sleep(2)
            
            # Les blocs sont dans #editorShowListContainer div.rowItem
            all_blocks = self.driver.find_elements(By.CSS_SELECTOR, "#editorShowListContainer div.rowItem")
            print(f"[INFO] {len(all_blocks)} blocs trouvés")
            
            # Limiter à max_blocks (10 par défaut)
            blocks_to_check = all_blocks[:max_blocks]
            print(f"[INFO] Vérification des {len(blocks_to_check)} premiers blocs...")
            
            # On doit TOUJOURS chercher par format - si pas de format, on ne modifie rien
            if not format_type:
                print(f"[ERREUR] Aucun format spécifié - impossible de sélectionner un bloc")
                return False
            
            # Patterns à chercher selon le format (scope = -s- ou - s -, flat = -f- ou - f -)
            if format_type.lower() == "scope":
                search_patterns = [" - s - ", "- s -", " -s- ", "-s-"]
            else:
                search_patterns = [" - f - ", "- f -", " -f- ", "-f-"]
            
            print(f"[INFO] Recherche d'un bloc avec format '{format_type}' (patterns: {search_patterns})...")
            
            for index, block in enumerate(blocks_to_check):
                block_title = block.text.split('\n')[0] if block.text else ""
                block_title_lower = block_title.lower()
                
                # Vérifier si un des patterns est présent
                if any(pattern in block_title_lower for pattern in search_patterns):
                    print(f"[INFO] Bloc trouvé: {block_title[:50]}... (index {index + 1})")
                    
                    # Cliquer sur le bouton "Open show in editor" (div.openShowBtn)
                    open_btn = block.find_element(By.CSS_SELECTOR, "div.openShowBtn")
                    open_btn.click()
                    
                    self.wait_for_page_load()
                    time.sleep(2)
                    
                    print(f"[INFO] Bloc ouvert dans l'éditeur")
                    return True
            
            # Aucun bloc avec le format trouvé - NE PAS MODIFIER
            print(f"[INFO] Aucun bloc avec format '{format_type}' trouvé dans les {max_blocks} premiers blocs")
            print(f"[INFO] Aucune modification effectuée - pas de bloc correspondant")
            return False
            
        except Exception as e:
            print(f"[ERREUR] Sélection bloc: {e}")
            return False
    
    def replace_film_in_block(self, new_film_name, new_block_name=None):
        """
        Remplace le film dans le bloc sélectionné par le nouveau film
        Workflow:
        1. Trouver et supprimer le film existant (sous le marqueur de volume) via icône poubelle
        2. Aller sur /#tabs-clips
        3. Trier par nouveaux à anciens
        4. Drag & drop le premier film sous le marqueur de volume
        
        Marqueur selon la salle:
        - Salle 2 (Selectotel): VOLUME_NORMAL
        - Salle 3 (Brunet): DCI_XYZ_FLAT
        
        Args:
            new_film_name: Nom du nouveau film à ajouter
            new_block_name: Nouveau nom pour le bloc (optionnel)
        """
        try:
            print(f"[INFO] Remplacement du film...")
            
            # Déterminer le marqueur selon la salle
            # Salle 2 (Selectotel) = VOLUME_NORMAL, Salle 3 (Brunet) = DCI_XYZ_FLAT
            if str(self.salle) == "2":
                volume_marker = "VOLUME_NORMAL"
            else:
                volume_marker = "DCI_XYZ_FLAT"
            print(f"[INFO] Marqueur de volume pour salle {self.salle}: {volume_marker}")
            
            # Étape 1: Supprimer le film existant (celui sous le marqueur de volume)
            print(f"[INFO] Recherche du film à supprimer (sous {volume_marker})...")
            try:
                # Trouver l'élément marqueur de volume
                dci_flat = self.wait.until(
                    EC.presence_of_element_located((By.XPATH, f"//*[contains(text(), '{volume_marker}')]"))
                )
                
                # Trouver le parent row et chercher l'élément suivant (le film à supprimer)
                # Le film est juste après DCI_XYZ_FLAT
                parent = dci_flat.find_element(By.XPATH, "./ancestor::div[contains(@class, 'row')]")
                next_row = parent.find_element(By.XPATH, "./following-sibling::div[contains(@class, 'row')][1]")
                
                # Cliquer sur l'icône poubelle dans cette row
                delete_icon = next_row.find_element(By.CSS_SELECTOR, "img[src*='trash'], img[src*='delete'], .delete-icon, .trash-icon")
                delete_icon.click()
                print("[INFO] Film supprimé")
                time.sleep(1)
                
                # Confirmer la suppression si popup
                try:
                    confirm = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((By.XPATH,
                            "//button[contains(text(), 'OK') or contains(text(), 'Yes') or contains(text(), 'Oui')]"))
                    )
                    confirm.click()
                except:
                    pass
            except Exception as e:
                print(f"[INFO] Pas de film à supprimer ou erreur: {e}")
            
            time.sleep(1)
            
            # Étape 2: Aller sur l'onglet Clips (/#tabs-clips)
            print("[INFO] Navigation vers l'onglet Clips...")
            clips_tab = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href='#tabs-clips'], [data-target='#tabs-clips']"))
            )
            clips_tab.click()
            
            self.wait_for_page_load()
            time.sleep(2)
            
            # Étape 3: Trier par nouveaux à anciens (Date d'importation nouveau-ancien)
            print("[INFO] Tri par Date d'importation (nouveau-ancien)...")
            try:
                sort_dropdown = self.wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#tabs-clips select.dropdownSort"))
                )
                select = Select(sort_dropdown)
                # Index 7 = "Date d'importation (nouveau-ancien)" selon le HTML fourni
                select.select_by_index(7)
                time.sleep(2)
            except Exception as e:
                print(f"[INFO] Tri déjà appliqué ou erreur: {e}")
            
            # Étape 4: Prendre le premier film et le drag & drop sous le marqueur de volume
            print(f"[INFO] Sélection du premier film et drag & drop sous {volume_marker}...")
            
            # Trouver le premier film dans la liste des clips
            first_clip = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#editorCplListContainer div.rowItem:first-child"))
            )
            
            # Trouver le handle de drag (div.moveRowHitArea)
            drag_handle = first_clip.find_element(By.CSS_SELECTOR, "div.moveRowHitArea")
            
            # Trouver la cible (zone sous le marqueur de volume)
            dci_flat_target = self.driver.find_element(By.XPATH, f"//*[contains(text(), '{volume_marker}')]/ancestor::div[contains(@class, 'row')]")
            
            # Effectuer le drag & drop
            actions = ActionChains(self.driver)
            actions.click_and_hold(drag_handle)
            actions.move_to_element(dci_flat_target)
            actions.move_by_offset(0, 50)  # Déplacer un peu en dessous
            actions.release()
            actions.perform()
            
            print(f"[INFO] Film ajouté sous {volume_marker}")
            time.sleep(2)
            
            # Sauvegarder les changements - cliquer sur l'image save.png
            print("[INFO] Sauvegarde des changements...")
            try:
                save_icon = self.wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "img[src*='save.png']"))
                )
                save_icon.click()
                time.sleep(1)
                
                # Le modal #setTitleModal s'ouvre - entrer le nom dans #txtTitle
                if new_block_name:
                    print(f"[INFO] Renommage du bloc en: {new_block_name}")
                    title_input = self.wait.until(
                        EC.presence_of_element_located((By.ID, "txtTitle"))
                    )
                    title_input.clear()
                    title_input.send_keys(new_block_name)
                    time.sleep(1)
                
                # Cliquer sur le bouton "Overwrite/Remplacer" (#btnSaveOK)
                overwrite_btn = self.wait.until(
                    EC.element_to_be_clickable((By.ID, "btnSaveOK"))
                )
                overwrite_btn.click()
                print("[INFO] Changements sauvegardés (Overwrite)")
            except Exception as e:
                print(f"[INFO] Sauvegarde: {e}")
            
            return True
            
        except Exception as e:
            print(f"[ERREUR] Remplacement film: {e}")
            return False
    
    def rename_block(self, new_name):
        """
        Renomme le bloc sélectionné
        
        Args:
            new_name: Nouveau nom pour le bloc
        """
        try:
            print(f"[INFO] Renommage du bloc en: {new_name}")
            
            # Chercher le champ de nom du bloc
            name_input = self.wait.until(
                EC.presence_of_element_located((By.XPATH,
                    "//input[@id='blockName' or @name='blockName' or @name='name' or contains(@class, 'name')]"
                    " | //input[contains(@placeholder, 'name') or contains(@placeholder, 'nom')]"))
            )
            
            # Effacer et entrer le nouveau nom
            name_input.clear()
            name_input.send_keys(new_name)
            
            print(f"[INFO] Bloc renommé en '{new_name}'")
            return True
            
        except Exception as e:
            print(f"[ERREUR] Renommage bloc: {e}")
            return False
    
    def import_qfc_film(self, qfc_file_path):
        """
        Importe un film au format QFC (méthode legacy pour import local)
        
        Args:
            qfc_file_path: Chemin vers le fichier QFC
        """
        try:
            print(f"[INFO] Import du film: {qfc_file_path}")
            
            # Cliquer sur le bouton Import
            import_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, 
                    "//button[contains(text(), 'Import') or contains(@id, 'import')]"
                    " | //*[@data-tr='IMPORT']"))
            )
            import_button.click()
            
            time.sleep(1)
            
            # Sélectionner le fichier QFC
            file_input = self.wait.until(
                EC.presence_of_element_located((By.XPATH, "//input[@type='file']"))
            )
            file_input.send_keys(qfc_file_path)
            
            # Confirmer l'import
            confirm_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, 
                    "//button[contains(text(), 'Confirm') or contains(text(), 'OK') or contains(text(), 'Confirmer')]"
                    " | //*[contains(@class, 'btn-primary')]"))
            )
            confirm_button.click()
            
            # Attendre la fin de l'import
            self.wait_long.until(
                EC.presence_of_element_located((By.XPATH, 
                    "//*[contains(@class, 'success') or contains(text(), 'Success') or contains(text(), 'Complete')]"))
            )
            
            print(f"[INFO] Film importé avec succès: {os.path.basename(qfc_file_path)}")
            return True
            
        except Exception as e:
            print(f"[ERREUR] Import QFC échoué: {e}")
            return False
            
    def import_all_qfc_from_folder(self, folder_path=None):
        """
        Importe tous les fichiers QFC d'un dossier
        
        Args:
            folder_path: Chemin du dossier (utilise QFC_FOLDER_PATH par défaut)
        """
        if folder_path is None:
            folder_path = QFC_FOLDER_PATH
            
        qfc_files = glob.glob(os.path.join(folder_path, "*.qfc"))
        
        if not qfc_files:
            print(f"[INFO] Aucun fichier QFC trouvé dans {folder_path}")
            return []
            
        print(f"[INFO] {len(qfc_files)} fichiers QFC trouvés")
        
        imported = []
        for qfc_file in qfc_files:
            if self.import_qfc_film(qfc_file):
                imported.append(qfc_file)
                
        return imported
        
    def set_volume(self, volume=None):
        """
        Configure le volume à 51 (ou valeur spécifiée)
        
        Args:
            volume: Niveau de volume (0-100), utilise DEFAULT_VOLUME (51) par défaut
        """
        if volume is None:
            volume = DEFAULT_VOLUME
            
        try:
            print(f"[INFO] Configuration du volume à {volume}")
            
            # Naviguer vers les paramètres audio dans Barco ICMP
            audio_settings = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, 
                    "//a[contains(text(), 'Audio') or contains(text(), 'Sound')]"
                    " | //div[contains(text(), 'Audio')]"
                    " | //*[@data-tr='AUDIO'] | //*[@data-tr='SOUND']"
                    " | //*[contains(@class, 'audio') and contains(@class, 'menu')]"))
            )
            audio_settings.click()
            
            self.wait_for_page_load()
            
            # Trouver le slider ou input de volume
            volume_input = self.wait.until(
                EC.presence_of_element_located((By.XPATH, 
                    "//input[@id='volume' or @name='volume' or contains(@class, 'volume')]"
                    " | //input[@type='range']"
                    " | //input[@type='number' and (contains(@id, 'volume') or contains(@name, 'volume'))]"))
            )
            
            # Effacer et définir la valeur
            self.driver.execute_script("arguments[0].value = '';", volume_input)
            volume_input.send_keys(str(volume))
            
            # Déclencher l'événement change
            self.driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", volume_input)
            
            time.sleep(1)
            
            # Appliquer les changements si bouton présent
            try:
                apply_button = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, 
                        "//button[contains(text(), 'Apply') or contains(text(), 'Appliquer') or contains(text(), 'Save')]"
                        " | //*[contains(@class, 'btn-primary') and (contains(text(), 'Apply') or contains(text(), 'Save'))]"))
                )
                apply_button.click()
            except:
                pass  # Pas de bouton Apply, changement automatique
            
            print(f"[INFO] Volume configuré à {volume}")
            return True
            
        except Exception as e:
            print(f"[ERREUR] Configuration volume: {e}")
            return False
            
    def create_block(self, block_name, film_name, format_type=None, start_time=None):
        """
        Crée un bloc de projection avec le format spécifié
        
        Args:
            block_name: Nom du bloc
            film_name: Nom du film à ajouter au bloc
            format_type: 'scope' ou 'flat' (utilise DEFAULT_FORMAT par défaut)
            start_time: Heure de début (format HH:MM)
        """
        if format_type is None:
            format_type = DEFAULT_FORMAT
            
        try:
            print(f"[INFO] Création du bloc: {block_name} - Format: {format_type}")
            
            # Naviguer vers la gestion des blocs
            blocks_menu = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Blocks') or contains(text(), 'Blocs') or contains(@id, 'blocks')]"))
            )
            blocks_menu.click()
            
            # Cliquer sur Nouveau bloc
            new_block_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'New') or contains(text(), 'Nouveau') or contains(@id, 'newBlock')]"))
            )
            new_block_button.click()
            
            # Remplir le nom du bloc
            block_name_input = self.wait.until(
                EC.presence_of_element_located((By.XPATH, "//input[@id='blockName' or @name='blockName']"))
            )
            block_name_input.clear()
            block_name_input.send_keys(block_name)
            
            # Sélectionner le format (Scope ou Flat)
            format_select = Select(self.driver.find_element(By.XPATH, "//select[@id='format' or @name='format' or contains(@class, 'format')]"))
            if format_type.lower() == "scope":
                format_select.select_by_visible_text("Scope (2.39:1)")
            else:
                format_select.select_by_visible_text("Flat (1.85:1)")
                
            # Ajouter le film au bloc
            add_content_button = self.driver.find_element(By.XPATH, "//button[contains(text(), 'Add Content') or contains(text(), 'Ajouter')]")
            add_content_button.click()
            
            # Sélectionner le film
            film_item = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, f"//div[contains(text(), '{film_name}') or contains(@title, '{film_name}')]"))
            )
            film_item.click()
            
            # Confirmer l'ajout
            confirm_add = self.driver.find_element(By.XPATH, "//button[contains(text(), 'Add') or contains(text(), 'Ajouter')]")
            confirm_add.click()
            
            # Sauvegarder le bloc
            save_button = self.driver.find_element(By.XPATH, "//button[contains(text(), 'Save') or contains(text(), 'Enregistrer')]")
            save_button.click()
            
            print(f"[INFO] Bloc '{block_name}' créé avec format {format_type.upper()}")
            return True
            
        except Exception as e:
            print(f"[ERREUR] Création bloc: {e}")
            return False
            
    def schedule_block(self, block_name, schedule_date, schedule_time):
        """
        Programme un bloc pour une date et heure spécifiques
        
        Args:
            block_name: Nom du bloc à programmer
            schedule_date: Date (format YYYY-MM-DD)
            schedule_time: Heure (format HH:MM)
        """
        try:
            print(f"[INFO] Programmation du bloc '{block_name}' pour {schedule_date} à {schedule_time}")
            
            # Naviguer vers le scheduler
            scheduler_menu = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Schedule') or contains(text(), 'Programmation') or contains(@id, 'schedule')]"))
            )
            scheduler_menu.click()
            
            # Cliquer sur Nouvelle programmation
            new_schedule_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'New') or contains(text(), 'Nouveau') or contains(@id, 'newSchedule')]"))
            )
            new_schedule_button.click()
            
            # Sélectionner le bloc
            block_select = Select(self.wait.until(
                EC.presence_of_element_located((By.XPATH, "//select[@id='blockSelect' or @name='block']"))
            ))
            block_select.select_by_visible_text(block_name)
            
            # Définir la date
            date_input = self.driver.find_element(By.XPATH, "//input[@type='date' or @id='scheduleDate']")
            date_input.clear()
            date_input.send_keys(schedule_date)
            
            # Définir l'heure
            time_input = self.driver.find_element(By.XPATH, "//input[@type='time' or @id='scheduleTime']")
            time_input.clear()
            time_input.send_keys(schedule_time)
            
            # Sauvegarder la programmation
            save_schedule = self.driver.find_element(By.XPATH, "//button[contains(text(), 'Save') or contains(text(), 'Enregistrer') or contains(text(), 'Schedule')]")
            save_schedule.click()
            
            # Attendre confirmation
            self.wait.until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'success') or contains(text(), 'Success') or contains(text(), 'Programmé')]"))
            )
            
            print(f"[INFO] Bloc '{block_name}' programmé pour {schedule_date} à {schedule_time}")
            return True
            
        except Exception as e:
            print(f"[ERREUR] Programmation bloc: {e}")
            return False
    
    def schedule_seances(self, block_name, minutes="00", date_debut=None, date_fin=None):
        """
        Programme les séances dans le scheduler pour une plage de 7 jours
        
        Workflow:
        1. Naviguer vers le scheduler et la bonne semaine
        2. Programmer le vendredi avec une séance à 18:50 (10 min avant pour les pubs)
        3. Copier le vendredi vers sam/dim/mer/jeu via le modal de copie
        4. Ajouter les séances 13h sur sam/dim seulement (après-midi)
        
        Horaires:
        - Si minutes=00 -> 18:50 (10 min avant pour les pubs)
        - Sinon -> 18h + minutes spécifiées
        - Sam/Dim: ajout séance 13h en plus
        
        Args:
            block_name: Nom du bloc à programmer
            minutes: Minutes de la séance (00, 15 ou 30)
            date_debut: Date de début (format DD/MM/YYYY) - vendredi
            date_fin: Date de fin (format DD/MM/YYYY) - jeudi
            
        Returns:
            bool: True si succès, False si erreur
            
        Codes d'erreur (dans les logs):
            SCH-001: Erreur navigation vers scheduler
            SCH-002: Erreur parsing dates
            SCH-003: Vendredi non trouvé
            SCH-004: Erreur ajout séance vendredi
            SCH-005: Erreur copie vers jour cible
            SCH-006: Erreur ajout séance après-midi sam/dim
            SCH-007: Erreur générale scheduler
        """
        from datetime import datetime
        
        try:
            logger.info("[SCH] Navigation vers le Scheduler...")
            
            # Navigation vers /#sms/scheduler
            scheduler_url = f"{self.barco_url}/#sms/scheduler"
            logger.info(f"Navigation vers {scheduler_url}")
            self.driver.get(scheduler_url)
            
            self.wait_for_page_load()
            time.sleep(3)
            
            # Calculer les heures avec 10 minutes avant pour les pubs
            # 00 -> 18:50 (10 min avant 19:00)
            # 15 -> 19:05 (10 min avant 19:15) et 13:05
            # 30 -> 19:20 (10 min avant 19:30) et 13:20
            if minutes == "00":
                heure_soir = 18
                minutes_soir = "50"
                heure_aprem = 12
                minutes_aprem = "50"
            elif minutes == "15":
                heure_soir = 19
                minutes_soir = "05"
                heure_aprem = 13
                minutes_aprem = "05"
            elif minutes == "30":
                heure_soir = 19
                minutes_soir = "20"
                heure_aprem = 13
                minutes_aprem = "20"
            else:
                # Fallback
                heure_soir = 18
                minutes_soir = "50"
                heure_aprem = 12
                minutes_aprem = "50"
            
            logger.info(f"Heure du soir: {heure_soir}:{minutes_soir}, Heure après-midi: {heure_aprem}:{minutes_aprem}")
            
            # Parser les dates de plage si fournies
            date_debut_dt = None
            date_fin_dt = None
            try:
                if date_debut:
                    parts = date_debut.split('/')
                    date_debut_dt = datetime(int(parts[2]), int(parts[1]), int(parts[0]))
                    logger.info(f"[SCH] Date début: {date_debut}")
                if date_fin:
                    parts = date_fin.split('/')
                    date_fin_dt = datetime(int(parts[2]), int(parts[1]), int(parts[0]))
                    logger.info(f"[SCH] Date fin: {date_fin}")
            except Exception as e:
                logger.error(f"[SCH-002] Erreur parsing dates: {e}")
                return False
            
            # Si une plage de dates est spécifiée, naviguer vers la bonne semaine
            if date_debut:
                self._navigate_to_date(date_debut)
                time.sleep(2)
            
            # === ÉTAPE 1: Trouver le vendredi et ajouter la séance du soir ===
            day_headers = self.driver.find_elements(By.CSS_SELECTOR, "div.timeLineHeader div.dayHeader")
            day_views = self.driver.find_elements(By.CSS_SELECTOR, "div.timLineViewArea div.dayView")
            
            vendredi_index = None
            vendredi_date = None
            
            for index, header in enumerate(day_headers):
                try:
                    day_name = header.find_element(By.CSS_SELECTOR, "p.day").text.lower().strip()
                    date_text = header.find_element(By.CSS_SELECTOR, "p.date").text.strip()
                    
                    if any(j in day_name for j in ['vendredi', 'friday', 'ven']):
                        # Vérifier si c'est le bon vendredi (dans la plage)
                        if date_debut_dt:
                            parts = date_text.split('/')
                            jour_dt = datetime(int(parts[2]), int(parts[1]), int(parts[0]))
                            if jour_dt >= date_debut_dt:
                                vendredi_index = index
                                vendredi_date = date_text
                                break
                        else:
                            vendredi_index = index
                            vendredi_date = date_text
                            break
                except:
                    continue
            
            if vendredi_index is None:
                logger.error("[SCH-003] Vendredi non trouvé dans le scheduler")
                print("[ERREUR SCH-003] Vendredi non trouvé dans le scheduler")
                return False
            
            logger.info(f"[SCH] === VENDREDI ({vendredi_date}) : Ajout séance {heure_soir}:{minutes_soir} ===")
            vendredi_view = day_views[vendredi_index]
            if not self._add_seance_at_hour(vendredi_view, heure_soir, minutes_soir):
                logger.error(f"[SCH-004] Échec ajout séance vendredi {heure_soir}:{minutes_soir}")
                print(f"[ERREUR SCH-004] Échec ajout séance vendredi")
            time.sleep(2)
            
            # === ÉTAPE 2: Copier le vendredi vers sam/dim/mer/jeu ===
            # Jours cibles à copier (numéro du jour dans le mois)
            jours_a_copier = []
            
            for index, header in enumerate(day_headers):
                if index == vendredi_index:
                    continue
                try:
                    day_name = header.find_element(By.CSS_SELECTOR, "p.day").text.lower().strip()
                    date_text = header.find_element(By.CSS_SELECTOR, "p.date").text.strip()
                    
                    # Vérifier si c'est un jour à copier (sam, dim, mer, jeu)
                    if any(j in day_name for j in ['samedi', 'saturday', 'sam', 'dimanche', 'sunday', 'dim', 
                                                    'mercredi', 'wednesday', 'mer', 'jeudi', 'thursday', 'jeu']):
                        # Vérifier si dans la plage
                        if date_debut_dt and date_fin_dt:
                            parts = date_text.split('/')
                            jour_dt = datetime(int(parts[2]), int(parts[1]), int(parts[0]))
                            if jour_dt < date_debut_dt or jour_dt > date_fin_dt:
                                continue
                        
                        # Extraire le numéro du jour
                        jour_num = int(date_text.split('/')[0])
                        jours_a_copier.append({
                            'index': index,
                            'name': day_name,
                            'date': date_text,
                            'jour_num': jour_num
                        })
                except:
                    continue
            
            logger.info(f"Jours à copier depuis vendredi: {[j['name'] for j in jours_a_copier]}")
            
            # Calculer les jours à copier basé sur la date de début (vendredi)
            # Sam = vendredi + 1, Dim = vendredi + 2, Mer = vendredi + 5, Jeu = vendredi + 6
            if date_debut_dt:
                vendredi_jour = int(date_debut.split('/')[0])
                # Calculer les jours cibles
                sam_jour = vendredi_jour + 1
                dim_jour = vendredi_jour + 2
                mer_jour = vendredi_jour + 5
                jeu_jour = vendredi_jour + 6
                
                jours_nums = [sam_jour, dim_jour, mer_jour, jeu_jour]
                logger.info(f"[SCH] Jours calculés à copier: sam={sam_jour}, dim={dim_jour}, mer={mer_jour}, jeu={jeu_jour}")
            else:
                jours_nums = [j['jour_num'] for j in jours_a_copier]
            
            if jours_nums:
                logger.info(f"[SCH] Copie vendredi vers jours: {jours_nums}")
                if not self._copy_vendredi_to_days(vendredi_index, jours_nums):
                    logger.error(f"[SCH-005] Échec copie vers jours {jours_nums}")
                    print(f"[ERREUR SCH-005] Échec copie vers jours cibles")
                time.sleep(2)
            
            # === ÉTAPE 3: Ajouter les séances après-midi sur sam/dim seulement ===
            # Rafraîchir les éléments après les copies
            time.sleep(2)
            day_headers = self.driver.find_elements(By.CSS_SELECTOR, "div.timeLineHeader div.dayHeader")
            day_views = self.driver.find_elements(By.CSS_SELECTOR, "div.timLineViewArea div.dayView")
            
            for index, header in enumerate(day_headers):
                if index >= len(day_views):
                    continue
                try:
                    day_name = header.find_element(By.CSS_SELECTOR, "p.day").text.lower().strip()
                    date_text = header.find_element(By.CSS_SELECTOR, "p.date").text.strip()
                    
                    # Seulement sam/dim pour la séance de l'après-midi
                    if any(j in day_name for j in ['samedi', 'saturday', 'sam', 'dimanche', 'sunday', 'dim']):
                        # Vérifier si dans la plage
                        if date_debut_dt and date_fin_dt:
                            parts = date_text.split('/')
                            jour_dt = datetime(int(parts[2]), int(parts[1]), int(parts[0]))
                            if jour_dt < date_debut_dt or jour_dt > date_fin_dt:
                                continue
                        
                        logger.info(f"[SCH] === {day_name.upper()} ({date_text}) : Ajout séance {heure_aprem}:{minutes_aprem} ===")
                        day_view = day_views[index]
                        if not self._add_seance_at_hour(day_view, heure_aprem, minutes_aprem):
                            logger.error(f"[SCH-006] Échec ajout séance après-midi {day_name}")
                            print(f"[ERREUR SCH-006] Échec ajout séance après-midi {day_name}")
                        time.sleep(2)
                except Exception as e:
                    logger.warning(f"[SCH] Erreur traitement jour {index}: {e}")
                    continue
            
            logger.info("[SCH] Programmation terminée avec succès")
            print("[INFO] Programmation terminée avec succès")
            return True
            
        except Exception as e:
            logger.error(f"[SCH-007] Erreur générale programmation scheduler: {e}")
            logger.debug(traceback.format_exc())
            print(f"[ERREUR SCH-007] Erreur programmation scheduler: {e}")
            return False
    
    def _copy_vendredi_to_days(self, vendredi_index, target_jours_nums):
        """
        Copie le vendredi vers plusieurs jours cibles via le modal de copie
        (sélection multiple dans le calendrier)
        
        Args:
            vendredi_index: Index du vendredi dans les en-têtes
            target_jours_nums: Liste des numéros de jours cibles (ex: [7, 8, 11, 12])
            
        Codes d'erreur:
            CPY-001: Index vendredi hors limites
            CPY-002: Dropdown vendredi non trouvé
            CPY-003: Bouton Copy Day non trouvé
            CPY-004: Modal date non ouvert
            CPY-005: Jour cible non trouvé dans calendrier
            CPY-006: Bouton OK non cliquable
            CPY-007: Erreur générale copie
        """
        try:
            # Récupérer l'en-tête du vendredi
            day_headers = self.driver.find_elements(By.CSS_SELECTOR, "div.timeLineHeader div.dayHeader")
            
            if vendredi_index >= len(day_headers):
                logger.error(f"[CPY-001] Index vendredi {vendredi_index} hors limites ({len(day_headers)} jours)")
                return False
            
            vendredi_header = day_headers[vendredi_index]
            
            # Cliquer sur l'en-tête du vendredi pour ouvrir le dropdown
            try:
                dropdown_toggle = vendredi_header.find_element(By.CSS_SELECTOR, "a.dropdown-toggle")
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", dropdown_toggle)
                time.sleep(0.5)
                dropdown_toggle.click()
                logger.info("[CPY] Dropdown vendredi ouvert")
                time.sleep(1.5)
            except Exception as e:
                logger.error(f"[CPY-002] Dropdown vendredi non trouvé: {e}")
                return False
            
            # Cliquer sur "Jour de la copie" (Copy Day) - chercher dans le dropdown ouvert
            try:
                # Chercher le lien copyDay dans le dropdown du vendredi
                copy_day_link = vendredi_header.find_element(By.CSS_SELECTOR, "ul.dropdown-menu a.copyDay")
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", copy_day_link)
                time.sleep(0.3)
                copy_day_link.click()
                logger.info("[CPY] Bouton 'Jour de la copie' cliqué")
                time.sleep(1)
            except Exception as e:
                logger.error(f"[CPY-003] Bouton Copy Day non trouvé: {e}")
                # Essayer de fermer le dropdown
                try:
                    self.driver.find_element(By.TAG_NAME, "body").click()
                except:
                    pass
                return False
            
            # Attendre que le modal de date s'ouvre
            try:
                self.wait.until(
                    EC.visibility_of_element_located((By.ID, "dateTimeModal"))
                )
                time.sleep(0.5)
            except TimeoutException:
                logger.error("[CPY-004] Modal date non ouvert (timeout)")
                return False
            
            # Trouver et cliquer sur TOUS les jours cibles dans le calendrier
            # Les jours sont dans td.day (pas .old, pas .new, pas .notSelectable, pas .source)
            # On doit re-récupérer les cellules après chaque clic car le DOM se met à jour
            
            jours_trouves = []
            jours_restants = list(target_jours_nums)  # Copie de la liste
            
            for jour_num in jours_restants:
                # Re-récupérer les cellules à chaque itération pour éviter stale element
                day_cells = self.driver.find_elements(By.CSS_SELECTOR, "#dateTimeModal td.day")
                
                for cell in day_cells:
                    try:
                        cell_classes = cell.get_attribute("class") or ""
                        cell_text = cell.text.strip()
                        
                        # Ignorer les jours non sélectionnables
                        if 'old' in cell_classes or 'new' in cell_classes or 'notSelectable' in cell_classes or 'source' in cell_classes:
                            continue
                        
                        # Vérifier si c'est le jour qu'on cherche
                        if cell_text == str(jour_num):
                            cell.click()
                            logger.info(f"[CPY] Date sélectionnée: jour {jour_num}")
                            jours_trouves.append(jour_num)
                            time.sleep(0.5)
                            break
                    except:
                        continue
            
            if not jours_trouves:
                logger.error(f"[CPY-005] Aucun jour trouvé dans le calendrier parmi {target_jours_nums}")
                # Fermer le modal
                try:
                    close_btn = self.driver.find_element(By.CSS_SELECTOR, "#dateTimeModal .close, #dateTimeModal button[data-dismiss='modal']")
                    close_btn.click()
                except:
                    pass
                return False
            
            logger.info(f"[CPY] {len(jours_trouves)} jours sélectionnés: {jours_trouves}")
            
            # Cliquer sur OK pour confirmer
            try:
                ok_btn = self.wait.until(
                    EC.element_to_be_clickable((By.ID, "confirmDateTimeBtn"))
                )
                time.sleep(0.5)
                ok_btn.click()
                logger.info(f"[CPY] Copie confirmée vers jours {jours_trouves}")
                time.sleep(1)
            except TimeoutException:
                logger.error("[CPY-006] Bouton OK non cliquable (timeout)")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"[CPY-007] Erreur générale copie vendredi vers jours {target_jours_nums}: {e}")
            return False
    
    def _navigate_to_date(self, target_date):
        """
        Navigue vers la semaine contenant la date cible dans le scheduler
        
        Args:
            target_date: Date au format DD/MM/YYYY
        """
        try:
            from datetime import datetime
            
            # Parser la date cible
            date_parts = target_date.split('/')
            target_day = int(date_parts[0])
            target_month = int(date_parts[1])
            target_year = int(date_parts[2])
            target_dt = datetime(target_year, target_month, target_day)
            
            # Récupérer la date actuellement affichée dans le scheduler
            # On cherche la première date visible dans les en-têtes
            day_headers = self.driver.find_elements(By.CSS_SELECTOR, "div.timeLineHeader div.dayHeader p.date")
            
            if not day_headers:
                logger.warning("Aucun en-tête de date trouvé")
                return
            
            # Parser la première date affichée
            first_date_text = day_headers[0].text.strip()  # Format: DD/MM/YYYY
            first_parts = first_date_text.split('/')
            first_day = int(first_parts[0])
            first_month = int(first_parts[1])
            first_year = int(first_parts[2])
            first_dt = datetime(first_year, first_month, first_day)
            
            # Calculer le nombre de semaines à avancer ou reculer
            diff_days = (target_dt - first_dt).days
            weeks_diff = diff_days // 7
            
            logger.info(f"Date affichée: {first_date_text}, cible: {target_date}, diff: {weeks_diff} semaines")
            
            # Naviguer vers la bonne semaine
            # Les boutons sont: div.nextHeader (flèche droite) et div.prevHeader (flèche gauche)
            if weeks_diff > 0:
                # Avancer vers le futur
                for i in range(weeks_diff):
                    logger.info(f"Navigation semaine suivante ({i+1}/{weeks_diff})...")
                    next_btn = self.driver.find_element(By.CSS_SELECTOR, "div.nextHeader")
                    next_btn.click()
                    time.sleep(1.5)
                    self.wait_for_page_load()
            elif weeks_diff < 0:
                # Reculer vers le passé
                for i in range(abs(weeks_diff)):
                    logger.info(f"Navigation semaine précédente ({i+1}/{abs(weeks_diff)})...")
                    prev_btn = self.driver.find_element(By.CSS_SELECTOR, "div.prevHeader")
                    prev_btn.click()
                    time.sleep(1.5)
                    self.wait_for_page_load()
            
            self.wait_for_page_load()
            
        except Exception as e:
            logger.warning(f"Erreur navigation vers date: {e}")
    
    def _find_vendredi_index(self):
        """
        Trouve l'index du vendredi dans les en-têtes du scheduler
        
        Returns:
            int: Index du vendredi (0-6) ou None si non trouvé
        """
        try:
            day_headers = self.driver.find_elements(By.CSS_SELECTOR, "div.timeLineHeader div.dayHeader")
            
            for index, header in enumerate(day_headers):
                try:
                    day_name = header.find_element(By.CSS_SELECTOR, "p.day").text.lower().strip()
                    if 'vendredi' in day_name or 'friday' in day_name or 'ven' in day_name:
                        return index
                except:
                    continue
            
            return None
            
        except Exception as e:
            logger.error(f"Erreur recherche vendredi: {e}")
            return None
    
    def _get_jours_cibles(self, vendredi_index, date_debut=None, date_fin=None):
        """
        Récupère les informations des jours cibles pour la copie
        (samedi, dimanche, mercredi, jeudi) dans la plage de dates spécifiée
        
        Args:
            vendredi_index: Index du vendredi (source)
            date_debut: Date de début (format DD/MM/YYYY) - optionnel
            date_fin: Date de fin (format DD/MM/YYYY) - optionnel
        
        Returns:
            list: Liste de dictionnaires avec index et date de chaque jour cible
        """
        from datetime import datetime
        
        jours_cibles = []
        try:
            day_headers = self.driver.find_elements(By.CSS_SELECTOR, "div.timeLineHeader div.dayHeader")
            
            # Jours à copier: samedi, dimanche, mercredi, jeudi
            jours_valides = ['samedi', 'saturday', 'sam', 
                            'dimanche', 'sunday', 'dim',
                            'mercredi', 'wednesday', 'mer',
                            'jeudi', 'thursday', 'jeu']
            
            # Parser les dates de plage si fournies
            date_debut_dt = None
            date_fin_dt = None
            if date_debut:
                parts = date_debut.split('/')
                date_debut_dt = datetime(int(parts[2]), int(parts[1]), int(parts[0]))
            if date_fin:
                parts = date_fin.split('/')
                date_fin_dt = datetime(int(parts[2]), int(parts[1]), int(parts[0]))
            
            for index, header in enumerate(day_headers):
                if index == vendredi_index:
                    continue  # Skip vendredi (source)
                try:
                    day_name = header.find_element(By.CSS_SELECTOR, "p.day").text.lower().strip()
                    date_text = header.find_element(By.CSS_SELECTOR, "p.date").text.strip()
                    
                    # Vérifier si c'est un jour valide
                    if not any(jour in day_name for jour in jours_valides):
                        continue
                    
                    # Vérifier si la date est dans la plage
                    if date_debut_dt and date_fin_dt:
                        try:
                            parts = date_text.split('/')
                            jour_dt = datetime(int(parts[2]), int(parts[1]), int(parts[0]))
                            if jour_dt < date_debut_dt or jour_dt > date_fin_dt:
                                logger.debug(f"Jour {date_text} hors plage, ignoré")
                                continue
                        except:
                            pass  # Si erreur de parsing, on inclut le jour
                    
                    jours_cibles.append({
                        'index': index,
                        'name': day_name,
                        'date': date_text
                    })
                except:
                    continue
            
        except Exception as e:
            logger.error(f"Erreur récupération jours cibles: {e}")
        
        return jours_cibles
    
    def _add_seance_at_hour(self, day_view, hour, minutes="00"):
        """
        Ajoute une séance à une heure donnée dans un jour
        
        Args:
            day_view: Element div.dayView du jour
            hour: Heure (12, 13, 18 ou 19)
            minutes: Minutes (00, 05, 15, 20, 50)
            
        Returns:
            bool: True si succès, False sinon
            
        Codes d'erreur:
            ADD-001: Ligne d'heure non trouvée
            ADD-002: Popover non ouvert (timeout)
            ADD-003: Menu déroulant séances non ouvert
            ADD-004: Liste des séances vide
            ADD-005: Bouton OK non cliquable
            ADD-006: Erreur générale ajout séance
        """
        try:
            # Trouver la ligne d'heure correspondante
            hour_lines = day_view.find_elements(By.CSS_SELECTOR, "div.hourLine")
            
            if len(hour_lines) <= hour:
                logger.error(f"[ADD-001] Ligne d'heure {hour} non trouvée ({len(hour_lines)} lignes disponibles)")
                return False
            
            target_line = hour_lines[hour]
            
            # Scroller vers l'élément
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_line)
            time.sleep(0.5)
            
            # Calculer l'offset Y pour les minutes
            # Chaque ligne d'heure fait environ 67px de hauteur
            # On utilise une table de correspondance pour plus de précision
            line_height = 67  # pixels par heure
            
            # Table de correspondance minutes -> offset Y (ajustée pour précision)
            # La ligne d'heure fait 67px, donc 67/60 = 1.117 px par minute
            # IMPORTANT: move_to_element positionne au CENTRE de l'élément (33.5px)
            # Donc offset = (minutes * 1.117) - 33.5 pour avoir la position depuis le centre
            # 00 min -> 0 - 33.5 = -34 (haut de la ligne)
            # 50 min -> 56 - 33.5 = 22 (bas de la ligne)
            minutes_offset_map = {
                "00": -34,   # 0 min: haut de la ligne (0 - 33.5)
                "05": -28,   # 5 min: (5.6 - 33.5) = -28
                "10": -22,   # 10 min: (11.2 - 33.5) = -22
                "15": -17,   # 15 min: (16.7 - 33.5) = -17
                "20": -11,   # 20 min: (22.3 - 33.5) = -11
                "30": 0,     # 30 min: centre de la ligne (33.5 - 33.5)
                "50": 22     # 50 min: (55.8 - 33.5) = 22
            }
            
            # Utiliser la table ou calculer si pas dans la table
            if minutes in minutes_offset_map:
                offset_y = minutes_offset_map[minutes]
            else:
                try:
                    minutes_int = int(minutes)
                except:
                    minutes_int = 0
                # Calculer depuis le centre: (minutes * 1.117) - 33.5
                offset_y = int((minutes_int / 60) * line_height) - 34
            
            logger.info(f"[ADD] Clic à {hour}h avec offset Y={offset_y}px pour {minutes} minutes")
            
            # Clic gauche sur la ligne d'heure pour ouvrir le popover
            actions = ActionChains(self.driver)
            actions.move_to_element(target_line)
            actions.move_by_offset(10, offset_y)
            actions.click()
            actions.perform()
            
            time.sleep(1)
            
            # Attendre que le popover s'ouvre
            try:
                # Cliquer sur le bouton caretBtn pour ouvrir le menu déroulant des séances
                try:
                    caret_button = self.wait.until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "button.caretBtn.btn.dropdown-toggle"))
                    )
                    caret_button.click()
                    logger.info("[ADD] Menu déroulant des séances ouvert")
                    time.sleep(1)
                except TimeoutException:
                    logger.error("[ADD-002] Popover non ouvert (timeout sur caretBtn)")
                    return False
                
                # Attendre que le menu #listOfShows soit visible
                try:
                    self.wait.until(
                        EC.visibility_of_element_located((By.ID, "listOfShows"))
                    )
                except TimeoutException:
                    logger.error("[ADD-003] Menu déroulant séances non ouvert (timeout)")
                    return False
                
                # Scroller vers le bas du menu pour voir toutes les séances
                list_of_shows = self.driver.find_element(By.ID, "listOfShows")
                self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", list_of_shows)
                time.sleep(0.5)
                
                # Sélectionner la DERNIÈRE séance dans #listOfShows (le film)
                show_items = self.driver.find_elements(By.CSS_SELECTOR, "#listOfShows li a")
                if show_items:
                    last_show = show_items[-1]  # Dernière séance de la liste
                    # Scroller vers l'élément pour le rendre visible
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", last_show)
                    time.sleep(0.3)
                    show_title = last_show.get_attribute("title") or last_show.text
                    last_show.click()
                    logger.info(f"[ADD] Séance film sélectionnée: {show_title[:50]}...")
                    time.sleep(1)
                else:
                    logger.error("[ADD-004] Aucune séance dans la liste")
                    return False
                
                # Cliquer sur img.ok (valid.png) pour confirmer le film
                try:
                    ok_button = self.wait.until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "img.ok.btn"))
                    )
                    ok_button.click()
                    logger.info(f"[ADD] Séance film ajoutée à {hour}:{minutes}")
                    time.sleep(1.5)
                except TimeoutException:
                    logger.error("[ADD-005] Bouton OK non cliquable (timeout)")
                    return False
                
                # === AJOUTER "Fermer lampe" après le film ===
                # Fermer lampe = 10 minutes après la fin du film
                # Film dure ~2h, donc Fermer lampe à hour + 2, offset = minutes + 10
                time.sleep(1.5)
                
                try:
                    # Re-récupérer les lignes d'heure depuis le MÊME day_view (éviter stale element)
                    # On utilise les hour_lines du day_view original passé en paramètre
                    hour_lines2 = day_view.find_elements(By.CSS_SELECTOR, "div.hourLine")
                    
                    # Calculer l'heure et les minutes pour Fermer lampe
                    # Film ~2h, donc fin à hour + 2, puis +10 min
                    try:
                        minutes_int = int(minutes)
                    except:
                        minutes_int = 0
                    
                    # Fermer lampe = (heure du film + 2h) + (minutes du film + 10min)
                    fermer_minutes = minutes_int + 10
                    fermer_hour = hour + 2
                    if fermer_minutes >= 60:
                        fermer_minutes -= 60
                        fermer_hour += 1
                    
                    # Calculer l'offset Y pour fermer_minutes en utilisant la même table que pour le film
                    fermer_minutes_str = f"{fermer_minutes:02d}"
                    if fermer_minutes_str in minutes_offset_map:
                        fermer_offset = minutes_offset_map[fermer_minutes_str]
                    else:
                        fermer_offset = int((fermer_minutes / 60) * line_height)
                    
                    if len(hour_lines2) > fermer_hour:
                        target_line2 = hour_lines2[fermer_hour]
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_line2)
                        time.sleep(1)
                        
                        # Retry logic pour le clic Fermer lampe (max 3 tentatives)
                        for attempt in range(3):
                            # Cliquer à fermer_hour:fermer_minutes
                            actions2 = ActionChains(self.driver)
                            actions2.move_to_element(target_line2)
                            actions2.move_by_offset(10, fermer_offset)
                            actions2.click()
                            actions2.perform()
                            logger.info(f"[ADD] Clic pour Fermer lampe à {fermer_hour}h{fermer_minutes:02d} (tentative {attempt+1})")
                            time.sleep(1.5)
                            
                            # Vérifier si le popover s'est ouvert
                            try:
                                caret_button2 = WebDriverWait(self.driver, 5).until(
                                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.caretBtn.btn.dropdown-toggle"))
                                )
                                caret_button2.click()
                                logger.info("[ADD] Menu déroulant ouvert pour Fermer lampe")
                                time.sleep(1)
                                break  # Succès, sortir de la boucle
                            except TimeoutException:
                                if attempt < 2:
                                    logger.warning(f"[ADD] Popover non ouvert, nouvelle tentative...")
                                    # Cliquer ailleurs pour fermer tout popover résiduel
                                    self.driver.find_element(By.TAG_NAME, "body").click()
                                    time.sleep(0.5)
                                    # Re-récupérer les lignes d'heure depuis le MÊME day_view
                                    hour_lines2 = day_view.find_elements(By.CSS_SELECTOR, "div.hourLine")
                                    if len(hour_lines2) > fermer_hour:
                                        target_line2 = hour_lines2[fermer_hour]
                                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_line2)
                                        time.sleep(0.5)
                                else:
                                    raise TimeoutException("Popover Fermer lampe non ouvert après 3 tentatives")
                        
                        # Attendre que le menu soit visible
                        self.wait.until(
                            EC.visibility_of_element_located((By.ID, "listOfShows"))
                        )
                        
                        # Sélectionner "Fermer lampe" - index différent selon la salle
                        # Salle 2: index 0 (1er dans la liste)
                        # Salle 3: index 1 (2ème dans la liste)
                        show_items2 = self.driver.find_elements(By.CSS_SELECTOR, "#listOfShows li a")
                        fermer_index = 0 if str(self.salle) == "2" else 1
                        if len(show_items2) > fermer_index:
                            fermer_lampe = show_items2[fermer_index]
                            fermer_title = fermer_lampe.get_attribute("title") or fermer_lampe.text
                            fermer_lampe.click()
                            logger.info(f"[ADD] Fermer lampe sélectionné: {fermer_title[:30]}...")
                            time.sleep(1)
                            
                            # Confirmer avec OK
                            ok_button2 = self.wait.until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, "img.ok.btn"))
                            )
                            ok_button2.click()
                            logger.info(f"[ADD] Fermer lampe ajouté après {hour}:{minutes}")
                            time.sleep(1)
                        else:
                            logger.warning("[ADD] Fermer lampe non trouvé (moins de séances)")
                except Exception as e:
                    logger.warning(f"[ADD] Erreur ajout Fermer lampe: {e}")
                
                return True
                
            except TimeoutException:
                logger.error("[ADD-002] Popover non trouvé ou timeout")
                return False
            except Exception as e:
                logger.error(f"[ADD-006] Erreur sélection séance: {e}")
                return False
            
        except Exception as e:
            logger.error(f"[ADD-006] Erreur générale ajout séance à {hour}h: {e}")
            return False
    
    def _copy_day_to_date(self, source_index, target_info):
        """
        Copie un jour vers une date cible
        
        Args:
            source_index: Index du jour source (vendredi)
            target_info: Dict avec 'index', 'name', 'date' du jour cible
        """
        try:
            logger.info(f"Copie vers {target_info['name']} ({target_info['date']})...")
            
            # Récupérer les en-têtes des jours
            day_headers = self.driver.find_elements(By.CSS_SELECTOR, "div.timeLineHeader div.dayHeader")
            
            if source_index >= len(day_headers):
                logger.error("Index source hors limites")
                return False
            
            source_header = day_headers[source_index]
            
            # Cliquer sur l'en-tête du jour source pour ouvrir le dropdown
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", source_header)
            time.sleep(0.5)
            
            # Cliquer sur le lien dropdown-toggle
            dropdown_toggle = source_header.find_element(By.CSS_SELECTOR, "a.dropdown-toggle")
            dropdown_toggle.click()
            time.sleep(1)
            
            # Cliquer sur "Jour de la copie" (copyDay)
            copy_option = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "a.copyDay"))
            )
            copy_option.click()
            time.sleep(1)
            
            # Le modal #dateTimeModal s'ouvre - sélectionner la date cible
            if not self._select_date_in_modal(target_info['date']):
                logger.warning(f"Échec sélection date {target_info['date']}")
                return False
            
            # Cliquer sur OK pour confirmer
            try:
                ok_btn = self.wait.until(
                    EC.element_to_be_clickable((By.ID, "confirmDateTimeBtn"))
                )
                # Attendre que le bouton ne soit plus disabled
                time.sleep(1)
                ok_btn.click()
                logger.info(f"Jour copié vers {target_info['name']}")
                time.sleep(2)
                return True
            except Exception as e:
                logger.error(f"Erreur confirmation copie: {e}")
                return False
            
        except Exception as e:
            logger.error(f"Erreur copie jour: {e}")
            return False
    
    def _select_date_in_modal(self, target_date):
        """
        Sélectionne une date dans le modal dateTimeModal
        
        Args:
            target_date: Date au format "DD/MM/YYYY" ou "DD/MM/YY"
            
        Returns:
            bool: True si succès
        """
        try:
            # Attendre que le modal soit visible
            self.wait.until(
                EC.visibility_of_element_located((By.ID, "dateTimeModal"))
            )
            time.sleep(1)
            
            # Extraire le jour de la date cible (ex: "05/02/2026" -> 5)
            date_parts = target_date.split('/')
            if len(date_parts) >= 2:
                target_day = int(date_parts[0])
            else:
                logger.error(f"Format de date invalide: {target_date}")
                return False
            
            # Trouver et cliquer sur le jour dans le calendrier
            # Les jours sont dans td.day (pas .old, pas .new pour le mois courant)
            day_cells = self.driver.find_elements(By.CSS_SELECTOR, "#datePicker .datepicker-days td.day")
            
            for cell in day_cells:
                cell_classes = cell.get_attribute("class")
                cell_text = cell.text.strip()
                
                # Ignorer les jours du mois précédent/suivant et les jours non sélectionnables
                if 'old' in cell_classes or 'new' in cell_classes or 'notSelectable' in cell_classes:
                    continue
                
                # Ignorer la cellule source
                if 'source' in cell_classes:
                    continue
                
                if cell_text == str(target_day):
                    cell.click()
                    logger.info(f"Date sélectionnée: jour {target_day}")
                    time.sleep(0.5)
                    return True
            
            logger.warning(f"Jour {target_day} non trouvé dans le calendrier")
            return False
            
        except Exception as e:
            logger.error(f"Erreur sélection date: {e}")
            return False
            
    def full_workflow_usb(self, film_name=None, block_name=None, format_type=None, schedule_date=None, schedule_time=None, block_number=None, minutes="00", max_blocks=10, date_debut=None, date_fin=None):
        """
        Workflow complet via Import USB (recommandé pour Barco ICMP):
        1. Login
        2. Navigation vers Import USB
        3. Sélection et import du film QFC (détection auto du format scope/flat)
        4. Navigation vers Éditeur de séance
        5. Sélection du bloc selon le format (-s- pour scope, -f- pour flat) dans les 10 premiers
        6. Remplacement de l'ancien film par le nouveau + renommage
        7. Configuration du volume à 51
        8. Programmation dans le scheduler (13h et 19h + minutes) pour la plage de dates
        
        Args:
            film_name: Nom du film QFC à importer (optionnel, prend le premier si None)
            block_name: Nouveau nom pour le bloc (optionnel)
            format_type: 'scope' ou 'flat' (auto-détecté si None)
            schedule_date: Date de programmation (optionnel)
            schedule_time: Heure de programmation (optionnel)
            block_number: Numéro du bloc (ignoré si format_type détecté, fallback sinon)
            minutes: Minutes de la séance (00, 15 ou 30)
            max_blocks: Nombre max de blocs à parcourir (par défaut 10)
            date_debut: Date de début du scheduling (format DD/MM/YYYY)
            date_fin: Date de fin du scheduling (format DD/MM/YYYY)
        """
        try:
            self.start_browser()
            
            # 1. Login
            if not self.login():
                return False
            
            # 2. Import QFC via USB
            print("[INFO] === ÉTAPE 1: IMPORT QFC VIA USB ===")
            if not self.import_qfc_from_usb(film_name):
                print("[ERREUR] Import QFC depuis USB échoué")
                return False
            
            # Récupérer le format détecté du film importé
            detected_format = getattr(self, 'imported_film_format', None) or format_type or 'scope'
            print(f"[INFO] Format détecté du film: {detected_format}")
            
            # Extraire le nom du film depuis le texte QFC importé
            imported_film_text = getattr(self, 'imported_film_text', None) or ""
            extracted_film_name = self.extract_film_name(imported_film_text) if imported_film_text else "Film"
            print(f"[INFO] Nom du film extrait: {extracted_film_name}")
            
            # Générer le nom du bloc au format: Salle - F/S - NomFilm
            # Utiliser le nom de la salle si défini, sinon "Brunet" par défaut
            salle_name = getattr(self, 'salle_name', None) or "Brunet"
            auto_block_name = self.generate_block_name(extracted_film_name, detected_format, salle=salle_name)
            print(f"[INFO] Nom du bloc généré: {auto_block_name}")
            
            # 3. Navigation vers Éditeur de séance
            print("[INFO] === ÉTAPE 2: ÉDITEUR DE SÉANCE ===")
            if not self.navigate_to_session_editor():
                print("[ERREUR] Navigation vers Éditeur de séance échouée")
                return False
            
            # 4. Sélectionner le bloc selon le format (scope = -s-, flat = -f-)
            print(f"[INFO] === ÉTAPE 3: SÉLECTION BLOC (format: {detected_format}, max: {max_blocks}) ===")
            if not self.select_block(block_number=block_number, format_type=detected_format, max_blocks=max_blocks):
                print(f"[ERREUR] Sélection du bloc échouée")
                return False
            
            # 5. Remplacer l'ancien film par le nouveau et renommer avec le nom auto-généré
            print("[INFO] === ÉTAPE 4: REMPLACEMENT FILM + RENOMMAGE ===")
            if not self.replace_film_in_block(extracted_film_name, auto_block_name):
                print("[ERREUR] Remplacement du film échoué")
                return False
            
            # 6. Programmation dans le scheduler
            print(f"[INFO] === ÉTAPE 5: PROGRAMMATION SCHEDULER (minutes: :{minutes}) ===")
            if date_debut and date_fin:
                print(f"[INFO] Plage de dates: {date_debut} -> {date_fin}")
            self.schedule_seances(auto_block_name, minutes, date_debut, date_fin)
                
            print("[INFO] ========================================")
            print("[INFO] WORKFLOW COMPLET TERMINÉ AVEC SUCCÈS!")
            print("[INFO] ========================================")
            return True
            
        except Exception as e:
            print(f"[ERREUR] Workflow USB: {e}")
            return False
            
        finally:
            self.close_browser()
    
    def full_workflow(self, qfc_files, block_name, format_type=None, schedule_date=None, schedule_time=None):
        """
        Workflow complet (méthode legacy pour import local):
        1. Import des films QFC
        2. Configuration du volume à 51
        3. Création d'un bloc avec le bon format
        4. Programmation si date/heure fournies
        
        Args:
            qfc_files: Liste de fichiers QFC ou chemin vers un dossier
            block_name: Nom du bloc à créer
            format_type: 'scope' ou 'flat'
            schedule_date: Date de programmation (optionnel)
            schedule_time: Heure de programmation (optionnel)
        """
        try:
            self.start_browser()
            
            if not self.login():
                return False
                
            # Import des films
            self.navigate_to_content_manager()
            
            if isinstance(qfc_files, str) and os.path.isdir(qfc_files):
                imported = self.import_all_qfc_from_folder(qfc_files)
            elif isinstance(qfc_files, list):
                imported = []
                for qfc_file in qfc_files:
                    if self.import_qfc_film(qfc_file):
                        imported.append(qfc_file)
            else:
                if self.import_qfc_film(qfc_files):
                    imported = [qfc_files]
                else:
                    imported = []
                    
            if not imported:
                print(f"[INFO] Aucun film importé")
                return []
                
            # Configuration du volume à 51
            self.set_volume(DEFAULT_VOLUME)
            
            # Création du bloc
            film_name = os.path.splitext(os.path.basename(imported[0]))[0]
            self.create_block(block_name, film_name, format_type)
            
            # Programmation si demandée
            if schedule_date and schedule_time:
                self.schedule_block(block_name, schedule_date, schedule_time)
                
            print("[INFO] Workflow complet terminé avec succès")
            return True
            
        except Exception as e:
            print(f"[ERREUR] Workflow: {e}")
            return False
            
        finally:
            self.close_browser()


if __name__ == "__main__":
    # Pour les tests directs, utiliser main.py à la place
    print("[INFO] Utilisez main.py pour lancer le bot")
    print("       python main.py")
