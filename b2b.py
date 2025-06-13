from playwright.sync_api import sync_playwright
import json
import os
import time

# 🔤 Letters A-Z
keywords = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
results = []

# 📁 Create output folder
os.makedirs("data", exist_ok=True)

# 🛡️ Detect Cloudflare block
def is_blocked_by_cloudflare(page):
    content = page.content()
    block_texts = [
        "Sorry, you have been blocked",
        "Attention Required!",
        "Checking your browser before accessing"
    ]
    return any(text in content for text in block_texts)

try:
    with sync_playwright() as p:
        # 🌐 Connect to BrightData browser over CDP
        browser = p.chromium.connect_over_cdp(
            "wss://brd-customer-hl_52bb577f-zone-scraping_browser1:i7xn5u2eiwx2@brd.superproxy.io:9222"
        )

        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/114.0.0.0 Safari/537.36"
            ),
            locale="fr-FR",
            viewport={"width": 1920, "height": 1080}
        )

        page = context.new_page()
        page.set_extra_http_headers({})  # No additional headers to avoid CDP issues

        for key in keywords:
            print(f"\n🔎 Lettre : {key}")
            page_number = 1

            while True:
                url = f"https://b2bhint.com/fr/search?q={key}&type=companies&page={page_number}"
                print(f" Page {page_number} : {url}")

                try:
                    page.goto(url, timeout=60000, wait_until="domcontentloaded")
                    page.wait_for_selector("table[class*='List_list'] tbody tr", timeout=45000)

                    # Scroll down to load all content
                    page.evaluate("""
                        () => new Promise((resolve) => {
                            let totalHeight = 0;
                            let distance = 100;
                            let timer = setInterval(() => {
                                window.scrollBy(0, distance);
                                totalHeight += distance;
                                if (totalHeight >= document.body.scrollHeight) {
                                    clearInterval(timer);
                                    resolve();
                                }
                            }, 200);
                        })
                    """)
                    time.sleep(5)

                    if is_blocked_by_cloudflare(page):
                        print("    ❌ BLOQUÉ PAR CLOUDFLARE - Passage à la lettre suivante.")
                        break

                    rows = page.query_selector_all("table[class*='List_list'] tbody tr")
                    if not rows:
                        print("    ✅ Aucun résultat trouvé. Fin de pagination.")
                        break

                    for row in rows:
                        try:
                            name = row.query_selector("a").inner_text().strip()
                            location_raw = row.query_selector("div > div > div:nth-child(2)").inner_text().strip()
                            parts = location_raw.split(" > ")
                            country = parts[0] if parts else "Inconnu"
                            identifier = parts[-1] if len(parts) > 1 else "Inconnu"
                            logo_el = row.query_selector("img[alt='Logo']")
                            logo_url = logo_el.get_attribute("src") if logo_el else "Aucun"

                            results.append({
                                "lettre": key,
                                "nom": name,
                                "country": country,
                                "identifier": identifier,
                                "page": page_number,
                                "logo_url": logo_url
                            })

                            print(f"    ✔ {name} ({country}, {identifier})")

                        except Exception as e:
                            print(f"    ⚠ Erreur dans une ligne : {e}")

                    time.sleep(3)
                    page_number += 1

                except Exception as e:
                    print(f"    ⚠ Erreur d'accès à la page : {e}")
                    if "Timeout" in str(e):
                        print("    ⏱️ Timeout détecté - Fin de la pagination.")
                    break

except KeyboardInterrupt:
    print("\n🛑 Interruption manuelle détectée. Sauvegarde des données...")

finally:
    try:
        if 'browser' in locals():
            browser.close()
    except:
        pass

    output_file = "data/entreprises_all.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)

    print(f"\n✅ Données sauvegardées dans : {output_file}")
    print(f"📊 Total entreprises collectées : {len(results)}")
