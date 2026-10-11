"""Cross-browser smoke test (used by CI):  python tests/browser_smoke.py [chromium|firefox|webkit]
Starts the app, then walks landing -> ID -> profile -> choice -> language -> consent -> 8 questions -> review -> submit,
and staff sign-in -> dashboard -> case page with chart. Fails on any page error."""
import os, subprocess, sys, tempfile, time, urllib.request
from playwright.sync_api import sync_playwright

browser_name = sys.argv[1] if len(sys.argv) > 1 else "chromium"
port = 8531
env = dict(os.environ, MANASETU_DATA_DIR=tempfile.mkdtemp(), PYTHONUTF8="1")
srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--log-level", "warning"], env=env)
base = f"http://127.0.0.1:{port}"
try:
    for _ in range(60):
        try: urllib.request.urlopen(base + "/api/meta", timeout=1); break
        except Exception: time.sleep(0.5)
    errors = []
    with sync_playwright() as p:
        b = getattr(p, browser_name).launch(); page = b.new_page(viewport={"width": 1280, "height": 900})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(base + "/"); page.click("[data-act=begin]"); page.fill("#pid", "CMP1021"); page.click("#idbtn"); page.wait_for_selector(".profile")
        page.click("[data-act=confirmme]"); page.click("[data-act=intent][data-d=yes]"); page.click("[data-act=langcontinue]"); page.wait_for_selector(".ack")
        for cb in page.query_selector_all("input[data-change=ackchg]"): cb.check()
        page.click("#consent-go"); page.wait_for_selector(".qtext")
        voice_btn = page.query_selector("[data-act=voicestart]")
        print(browser_name, "voice button offered:", voice_btn is not None, "(Firefox/WebKit normally have no SpeechRecognition -> expected False)")
        for _ in range(8):
            page.click("[data-act=answer][data-v='1']"); page.wait_for_selector("[data-act=qnext]:not([disabled])"); page.click("[data-act=qnext]"); page.wait_for_timeout(100)
        page.wait_for_selector("#submitbtn"); page.click("#submitbtn"); page.wait_for_selector(".card.tint")
        page.goto(base + "/#/staff"); page.fill("#u", "clinician1"); page.fill("#p", "Clinician#2026"); page.click("#loginbtn"); page.wait_for_selector(".stat")
        page.goto(base + "/#/case/CMP1021"); page.wait_for_selector("#histchart"); page.wait_for_timeout(500)
        b.close()
    assert not errors, errors
    print(browser_name, "OK")
finally:
    srv.terminate()
