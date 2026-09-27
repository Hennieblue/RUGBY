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

    images = driver.find_elements(
        By.CSS_SELECTOR,
        "img[alt]",
    )

    for img in images:
        try:
            alt = clean(
                img.get_attribute("alt")
            )

            if (
                not alt
                or alt.lower() in {
                    "image",
                    "logo",
                }
            ):
                continue

            el = img

            for _ in range(12):
                el = el.find_element(
                    By.XPATH,
                    "..",
                )

                text = clean(el.text)

                if not text or len(text) > 1200:
                    continue

                alts = []

                for other in el.find_elements(
                    By.CSS_SELECTOR,
                    "img[alt]",
                ):
                    a = clean(
                        other.get_attribute("alt")
                    )

                    if (
                        a
                        and a.lower()
                        not in {
                            "image",
                            "logo",
                        }
                        and a not in alts
                    ):
                        alts.append(a)

                if len(alts) < 2:
                    continue

                href = ""

                links = el.find_elements(
                    By.CSS_SELECTOR,
                    'a[href*="/live/"]',
                )

                if links:
                    href = (
                        links[0]
                        .get_attribute("href")
                        or ""
                    )

                if not href:
                    links = el.find_elements(
                        By.CSS_SELECTOR,
                        "a[href]",
                    )

                    for link in links:
                        h = (
                            link.get_attribute(
                                "href"
                            )
                            or ""
                        )

                        if h:
                            href = h
                            break

                if not href:
                    continue

                key = (
                    href,
                    alts[0],
                    alts[1],
                )

                if key not in seen:
                    seen.add(key)
                    result.append(
                        (el, href)
                    )

                break

        except Exception:
            pass

    return result
def read_matches(driver):
    driver.get(URL)
    WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME,"body")))
    time.sleep(3); driver.execute_script("window.scrollTo(0,document.body.scrollHeight)"); time.sleep(1); driver.execute_script("window.scrollTo(0,0)")
    matches, seen = [], set()
    for el, href in containers(driver):
        try:
            alts=[]
            for img in el.find_elements(By.CSS_SELECTOR,"img[alt]"):
                a=clean(img.get_attribute("alt"))
                if a and a.lower() not in {"image","logo"} and a not in alts: alts.append(a)
            slug=re.search(r"/live/([^/?#]+)",href)
            teams=[clean(x.replace("-"," ")) for x in (slug.group(1).split("-vs-") if slug else [])]
            if len(alts)>=2: home,away=alts[-2],alts[-1]
            elif len(teams)==2: home,away=teams
            else: continue
            key=(home.lower(),away.lower())
            if key in seen: continue
            seen.add(key)
            kickoff,status=parse_card(el.text)
            if status=="FINISHED": continue
            hs,aws=first_text(el,".score.home"),first_text(el,".score.away")
            score=f"{int(hs)} - {int(aws)}" if hs.isdigit() and aws.isdigit() else "0 - 0"
            if status=="UPCOMING": score="0 - 0"
            matches.append({"home":home,"away":away,"kickoff":kickoff,"status":status,"score":score,"url":href,"commentary":[],"commentary_note":"No key events yet."})
        except Exception: pass
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
    driver=make_driver()
    try:
        matches=read_matches(driver)

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

        for match in matches:
            add_commentary(driver,match)

        payload={"updated":datetime.now(SA).strftime("%Y-%m-%d %H:%M:%S SAST"),"matches":matches}
        OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
        print(f"Saved {len(matches)} matches")
    finally:
        driver.quit()

if __name__=="__main__": main()
