import json
import re
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

URL = "https://rugby365.com/results/"
OUT = Path(__file__).with_name("data.json")
SA = ZoneInfo("Africa/Johannesburg")
EVENT_NAMES = {"try":"TRY","con":"CONVERSION","pg":"PENALTY GOAL","dg":"DROP GOAL","yc":"YELLOW CARD","rc":"RED CARD","sub":"SUBSTITUTION"}

def clean(value): return re.sub(r"\s+", " ", value or "").strip()

def first_text(parent, selector, default=""):
    found = parent.find_elements(By.CSS_SELECTOR, selector)
    return clean(found[0].text) if found else default

def make_driver():
    o = webdriver.ChromeOptions()
    for arg in ("--headless=new","--window-size=1920,1080","--disable-gpu","--no-sandbox","--disable-dev-shm-usage","--lang=en-ZA"):
        o.add_argument(arg)
    d = webdriver.Chrome(options=o)
    d.set_page_load_timeout(60)
    return d

def future_kickoff(kickoff):
    m = re.match(r"^(\d{1,2}):(\d{2})\s*(am|pm)?$", kickoff.strip(), re.I)
    if not m: return None
    hour, minute, ap = int(m.group(1)), int(m.group(2)), (m.group(3) or "").lower()
    if ap == "pm" and hour != 12: hour += 12
    if ap == "am" and hour == 12: hour = 0
    now = datetime.now(SA)
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0) > now

def parse_card(text):
    tm = re.search(r"\b(\d{1,2}:\d{2}\s*(?:am|pm)?)(?:\s*SAST)?\b", clean(text), re.I)
    kickoff = clean(tm.group(1)) if tm else ""
    status = "FINISHED" if re.search(r"\bFT\b", text, re.I) else "LIVE" if re.search(r"\bLIVE\b", text, re.I) else "UPCOMING"
    if status != "FINISHED" and future_kickoff(kickoff) is True: status = "UPCOMING"
    return kickoff, status

def containers(driver):
    result = []
    seen = set()

    links = driver.find_elements(
        By.CSS_SELECTOR,
        'a[href*="/live/"]'
    )

    print("LIVE LINKS FOUND:", len(links))

    for link in links:
        try:
            href = link.get_attribute("href") or ""

            # Slegs werklike wedstryd-skakels.
            match = re.search(
                r"/live/([^/?#]+)-vs-([^/?#]+)",
                href,
                re.I
            )

            if not match:
                continue

            key = href.split("?")[0].lower()

            if key in seen:
                continue

            seen.add(key)

            # Kry die naaste element wat die wedstryd se
            # inligting bevat.
            el = link

            for _ in range(12):
                el = el.find_element(
                    By.XPATH,
                    ".."
                )

                text = clean(el.text)

                if text:
                    alts = []

                    for img in el.find_elements(
                        By.CSS_SELECTOR,
                        "img[alt]"
                    ):
                        a = clean(
                            img.get_attribute("alt")
                        )

                        if (
                            a
                            and a.lower()
                            not in {
                                "image",
                                "logo",
                                "company logo",
                                "powered by onetrust"
                            }
                            and a not in alts
                        ):
                            alts.append(a)

                    # 'n Kaart met minstens twee spanname-prente
                    # is die een wat ons wil hê.
                    if len(alts) >= 2:
                        result.append(
                            (el, href)
                        )
                        break

            else:
                # As die spanname-prente nie beskikbaar is nie,
                # gebruik steeds die live-link.
                result.append(
                    (link, href)
                )

        except Exception as e:
            print(
                "CONTAINER ERROR:",
                str(e)[:150]
            )

    print(
        "MATCH CONTAINERS FOUND:",
        len(result)
    )

    return result
def read_matches(driver):
    driver.get(URL)

    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located(
            (By.TAG_NAME, "body")
        )
    )

    time.sleep(3)

    driver.execute_script(
        "window.scrollTo(0,document.body.scrollHeight)"
    )

    time.sleep(2)

    driver.execute_script(
        "window.scrollTo(0,0)"
    )

    time.sleep(1)

    matches = []
    seen = set()

    for el, href in containers(driver):
        try:
            slug = re.search(
                r"/live/([^/?#]+)",
                href,
                re.I
            )

            if not slug:
                continue

            slug_text = slug.group(1)

            parts = re.split(
                r"-vs-",
                slug_text,
                flags=re.I
            )

            if len(parts) != 2:
                continue

            home = clean(
                parts[0].replace("-", " ")
            )

            away = clean(
                parts[1].replace("-", " ")
            )

            if not home or not away:
                continue

            key = (
                home.lower(),
                away.lower()
            )

            if key in seen:
                continue

            seen.add(key)

            text = clean(el.text)

            kickoff, status = parse_card(text)

            hs = first_text(
                el,
                ".score.home"
            )

            aws = first_text(
                el,
                ".score.away"
            )

            if (
                hs.isdigit()
                and aws.isdigit()
            ):
                score = (
                    f"{int(hs)} - "
                    f"{int(aws)}"
                )
            else:
                # Probeer 'n gewone score uit die
                # kaart se teks te kry.
                score_match = re.search(
                    r"\b(\d+)\s*-\s*(\d+)\b",
                    text
                )

                if score_match:
                    score = (
                        f"{int(score_match.group(1))} - "
                        f"{int(score_match.group(2))}"
                    )
                else:
                    score = "0 - 0"

            if status == "UPCOMING":
                score = "0 - 0"

            matches.append({
                "home": home,
                "away": away,
                "kickoff": kickoff,
                "status": status,
                "score": score,
                "commentary": []
            })

        except Exception as e:
            print(
                "MATCH ERROR:",
                str(e)[:150]
            )

    return matches
def add_commentary(driver, match):
    try:
        driver.get(match["url"]); WebDriverWait(driver,20).until(EC.presence_of_element_located((By.CSS_SELECTOR,".game-header"))); time.sleep(.7)
        events=driver.find_elements(By.CSS_SELECTOR,".key-events-container .key-event")
        lines=[]
        for event in reversed(events):
            interval=first_text(event,".interval")
            if interval: lines.append(interval.upper()); continue
            hp,ap=first_text(event,".side.home .name"),first_text(event,".side.away .name")
            player=hp or ap or "Unknown player"; team=match["home"] if hp else match["away"] if ap else "Unknown team"
            kind="EVENT"
            icons=event.find_elements(By.CSS_SELECTOR,".icon-image")
            if icons:
                for c in (icons[0].get_attribute("class") or "").split():
                    if c in EVENT_NAMES: kind=EVENT_NAMES[c]; break
            minute,label=first_text(event,".score .time"),first_text(event,".score .label")
            line=((minute+" ") if minute else "")+f"{team} - {kind}: {player}"+((f". Score: {label}") if label else "")
            lines.append(line)
        match["commentary"]=lines
    except Exception as e:
        match["commentary_note"]="Commentary is not available yet."

def main():
    driver = make_driver()

    try:
        matches = read_matches(driver)

        for match in matches:
            print(
                "FOUND:",
                match["home"],
                "vs",
                match["away"],
                "-",
                match["status"],
                "-",
                match["score"],
            )

        print("COMMENTARY SKIPPED FOR TEST")
        print("ONESIGNAL TEST SKIPPED")

        payload = {
            "updated": datetime.now(SA).strftime(
                "%Y-%m-%d %H:%M:%S SAST"
            ),
            "matches": matches
        }

        OUT.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

        print(
            f"Saved {len(matches)} matches"
        )

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
