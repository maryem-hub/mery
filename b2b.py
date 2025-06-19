from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
import undetected_chromedriver as uc
import json
import time
import os
from datetime import datetime

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

os.makedirs("data", exist_ok=True)

def create_driver(headless=False):
    options = uc.ChromeOptions()
    options.headless = headless
    driver = uc.Chrome(options=options)
    driver.set_page_load_timeout(30)
    return driver

def is_blocked(page_source):
    block_phrases = ["checking your browser", "you have been blocked", "attention required"]
    lower_source = page_source.lower()
    return any(phrase in lower_source for phrase in block_phrases)

def wait_for_element(driver, by, selector, timeout=30):
    try:
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, selector)))
        return True
    except TimeoutException:
        return False

def extraire_resume_complet(driver, url, max_retries=3):
    """
    Extrait toutes les infos textuelles disponibles sur la page de détail entreprise.
    """
    for attempt in range(1, max_retries + 1):
        try:
            log(f"Chargement page détail ({attempt}/{max_retries}): {url}")
            driver.get(url)
            
            # Attendre le titre (ex h1) ou dl/h3 comme indicateurs de contenu chargé
            if not wait_for_element(driver, By.TAG_NAME, "h1", timeout=10) and \
               not wait_for_element(driver, By.TAG_NAME, "dl", timeout=10) and \
               not wait_for_element(driver, By.TAG_NAME, "h3", timeout=10):
                log(f"⚠ Aucun contenu principal trouvé rapidement sur la page : {url}")
            
            time.sleep(2)  # délai supplémentaire
            driver.execute_script("window.stop();")

            page_source = driver.page_source.lower()
            if "404" in page_source or "page not found" in page_source:
                log(f"❌ Page introuvable : {url}")
                return None
            if is_blocked(page_source):
                log(f"⛔ Bloqué par Cloudflare : {url}")
                return None

            data = {}

            # Extraire paires dt/dd dans tous les dl
            dl_elements = driver.find_elements(By.TAG_NAME, "dl")
            for dl in dl_elements:
                divs = dl.find_elements(By.XPATH, "./div")
                for div in divs:
                    try:
                        key = div.find_element(By.TAG_NAME, "dt").text.strip()
                        value = div.find_element(By.TAG_NAME, "dd").text.strip()
                        if key:
                            data[key] = value
                    except NoSuchElementException:
                        continue

            # Extraire tous les h3 + contenu sibling suivant
            h3_elements = driver.find_elements(By.TAG_NAME, "h3")
            for h3 in h3_elements:
                try:
                    key = h3.text.strip()
                    sibling = h3.find_element(By.XPATH, "following-sibling::*[1]")
                    value = sibling.text.strip()
                    if key:
                        if key in data:
                            data[key] += "\n" + value
                        else:
                            data[key] = value
                except NoSuchElementException:
                    continue

            return data

        except WebDriverException as e:
            log(f"⚠ Erreur WebDriver (tentative {attempt}) : {e}")
            time.sleep(attempt * 4)
        except Exception as e:
            log(f"⚠ Autre erreur (tentative {attempt}) : {e}")
            time.sleep(attempt * 4)

    log(f"❌ Échec définitif pour {url}")
    return None

def scrape_page(driver, lettre='A', page_number=1):
    url = f"https://b2bhint.com/fr/search?q={lettre}&type=companies&page={page_number}"
    log(f"🔎 Chargement page liste : {url}")
    try:
        driver.get(url)
    except WebDriverException as e:
        log(f"Erreur chargement page liste : {e}")
        return []

    time.sleep(3)

    page_source = driver.page_source.lower()
    if is_blocked(page_source):
        log("⛔ Accès bloqué par Cloudflare. Arrêt du script.")
        return []

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, "//table[contains(@class, 'List_list')]//tbody/tr"))
        )
    except TimeoutException:
        log("⏱ Timeout ou aucun résultat sur la page.")
        return []

    rows = driver.find_elements(By.XPATH, "//table[contains(@class, 'List_list')]//tbody/tr")
    companies = []
    for row in rows:
        try:
            name_el = row.find_element(By.TAG_NAME, "a")
            name = name_el.text.strip()
            link = name_el.get_attribute("href")
            location_el = row.find_elements(By.CSS_SELECTOR, "div > div > div:nth-child(2)")
            if location_el:
                lines = location_el[0].text.strip().split("\n")
                country = lines[0] if len(lines) >= 1 else "Inconnu"
                region_id = lines[1] if len(lines) >= 2 else "Inconnu"
            else:
                country = region_id = "Inconnu"
            companies.append({"name": name, "link": link, "country": country, "region_id": region_id})
        except Exception as e:
            log(f"❌ Erreur extraction ligne entreprise : {e}")

    # Éliminer les doublons d'URL
    seen_links = set()
    unique_companies = []
    for comp in companies:
        if comp["link"] not in seen_links:
            seen_links.add(comp["link"])
            unique_companies.append(comp)

    results = []
    for comp in unique_companies:
        log(f"➡ Traitement : {comp['name']} ({comp['country']} > {comp['region_id']})")
        details = extraire_resume_complet(driver, comp["link"])
        if details:
            results.append({
                "lettre": lettre,
                "nom": comp["name"],
                "country": comp["country"],
                "region_id": comp["region_id"],
                "page": page_number,
                "details": details
            })
        else:
            log("→ Détails indisponibles.")

    return results

def main():
    lettre = input("Lettre à scraper (A-Z) ? ").strip().upper()
    if len(lettre) != 1 or not lettre.isalpha():
        print("Lettre invalide. Veuillez entrer une lettre unique de A à Z.")
        return

    driver = create_driver(headless=False)  # Change to True pour mode headless
    page_number = 1

    try:
        results = scrape_page(driver, lettre, page_number)

        output_file = f"data/test_lettre_{lettre}page{page_number}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=4)

        log(f"✅ Fichier sauvegardé : {output_file}")

    except Exception as e:
        log(f"Erreur fatale : {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
