"""Browser interaction fixtures: all API calls intercepted; no real mutations."""
import copy
import io
import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from PIL import Image
import requests
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent


def main():
    session = requests.Session()
    session.trust_env = False
    session.headers["Authorization"] = "Bearer " + (ROOT/"local_operations/admin.key").read_text().strip()
    saved = {path: session.get("http://127.0.0.1:8765/api/"+path, timeout=20).json()
             for path in ("model", "snapshot", "blocks", "chain")}
    hospitals = [{"id": str(i), "code": "TEST_"+str(i), "name": "Fixture Hospital",
                  "wallet": "0x"+"1"*40, "status": "approved", "online": True,
                  "updated": "fixture", "heartbeat": None, "readiness": "{}",
                  "reconciliation_ok": True} for i in range(3)]
    config = {"id": "registered_fedprox_v1", "algorithm": "FedProx", "local_epochs": 3,
              "mu": .01, "seed": 42, "max_rounds": 20}
    campaign = {"registration": {"id": "fixture", "rounds": 1, "configuration": config,
                                "participants": hospitals},
                "status": {"state": "registered"}, "control": "run", "rounds": [],
                "participation": [{"joined": False}], "feedback": []}
    workflow = {"campaigns": [campaign], "approved_configurations": [config],
                "clients": [{"hospital": str(i), "authorized_consent": True, "data": {
                    "version": "fixture", "train_images": 4, "val_images": 4,
                    "class_counts": {"NORMAL": 2, "PNEUMONIA": 2}}} for i in range(3)],
                "data_folder": "fixture-only"}
    result = {"scope": "Real Edge browser; intercepted API fixtures, not real training or wallet extension",
              "checks": [], "errors": []}
    calls = []
    state={"registered":True}
    def handler(route):
        path = urlparse(route.request.url).path.removeprefix("/api/")
        try:
            body = route.request.post_data_json if route.request.method == "POST" and "json" in route.request.headers.get("content-type","") else {}
        except Exception:
            body = {}
        calls.append((path, body))
        data = copy.deepcopy(saved.get(path, {"ok": True}))
        if path == "hospitals/admin":
            data = {"hospitals": hospitals, "directory": {"connected": True}, "events": [], "rosters": []}
        elif path == "hospitals/me":
            data = {"wallet": hospitals[0]["wallet"], "application": hospitals[0] if state["registered"] else None}
        elif path == "hospitals/register":
            state["registered"]=True;data={"id":"0"}
        elif path == "current-blocks":
            query=parse_qs(urlparse(route.request.url).query);end=int(query.get("end",["60"])[0]);start=max(0,end-24)
            blocks=[]
            for number in range(start,end+1):
                events=[]
                if number in [4,8,10,11]:events=[{"event":"MembershipChanged","title":"Hospital approved: FIXTURE","category":"membership","arguments":{"wallet":"fixture","authorized":True}}]
                transactions=[{"transaction_hash":"0xfixture","status":1,"from":"fixture","to":"fixture","contract_name":"Hospital directory","description":"Contract transaction","events":events}]
                blocks.append({"block_number":number,"block_hash":"0x"+str(number).zfill(64),"parent_hash":"0xparent","timestamp":"fixture","transaction_count":1,"transactions":transactions})
            data={"network":"Fixture Hardhat","chain_id":31337,"instance_id":"0xfixture_instance","latest_block":60,"start_block":start,"end_block":end,"older_end":start-1 if start else None,"newer_end":min(60,end+25) if end<60 else None,"blocks":blocks}
        elif path == "hospitals/challenge": data = {"message": "Fixture login"}
        elif path == "hospitals/login": data = {"token": "fixture-session"}
        elif path == "hospitals/heartbeat": data = {"received_utc": "fixture"}
        elif path in ("workflow/admin", "workflow/me"): data = workflow
        elif path == "workflow/connectivity": data = {"ipfs": {"connected": True}, "blockchain": {"connected": True}}
        elif path == "workflow/create": data = {"id": "fixture"}
        elif path == "workflow/prepare-agent": data = {"message": "Fixture consent", "delegate": "fixture", "data_folder": "fixture"}
        elif path == "predict": data = {"predicted_class": "NORMAL", "model_scores": {"NORMAL": .7, "PNEUMONIA": .3},
                                     "global_version": 1, "inference_utc": "fixture", "cid": "fixture"}
        elif path == "log": data = {"log_tail": "Fixture log"}
        elif path == "verify": data = {"verified_utc": "fixture"}
        route.fulfill(json=data)

    def check(name, ok):
        result["checks"].append({"name": name, "passed": bool(ok)})
        print(name, bool(ok), flush=True)
        if not ok: raise AssertionError(name)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        try:
            for role in ("admin", "hospital"):
                context = browser.new_context(viewport={"width": 1440, "height": 1000})
                context.route("**/api/**", handler)
                context.add_init_script("window.ethereum={request:async p=>p.method==='eth_requestAccounts'?['0x'+'1'.repeat(40)]:'fixture-signature'}")
                page = context.new_page()
                page.on("pageerror", lambda error: result["errors"].append(str(error)))
                page.goto("http://127.0.0.1:8765/"+role)
                page.set_default_timeout(10000)
                def click(identity, endpoint=None):
                    before = len(calls)
                    for detail in page.locator("#"+identity).locator("xpath=ancestor::details[not(@open)]").all():
                        detail.locator(":scope > summary").click()
                    page.locator("#"+identity).click()
                    if endpoint:
                        page.wait_for_timeout(120)
                        check(role+" / "+identity, any(x[0] == endpoint for x in calls[before:]))
                    else:
                        check(role+" / "+identity, True)
                if role == "admin":
                    page.locator("#loginToken").fill("fixture-admin")
                    click("adminSignIn", "hospitals/admin")
                    page.locator("#opsCampaign").wait_for(state="visible")
                    click("chainRefresh","current-blocks")
                    click("chainOlder","current-blocks")
                    click("chainNewer","current-blocks")
                    page.locator("#chainNumber").fill("4")
                    click("chainGo","current-blocks")
                    page.wait_for_function("document.getElementById('currentBlockJson').textContent.includes('\"block_number\": 4')")
                    check("admin / live block lookup", json.loads(page.locator("#currentBlockJson").text_content())["block_number"]==4)
                    page.locator("#chainCategory").select_option("membership")
                    page.locator("#currentChainCards button").first.click()
                    check("admin / membership event details", "authorized" in page.locator("#currentBlockDetails").text_content())
                    page.wait_for_timeout(250)
                    for identity, endpoint in [("opsRefresh","workflow/connectivity"),("adminLoad","hospitals/admin")]:
                        click(identity, endpoint)
                    page.locator("#hospitalReason").fill("Fixture review")
                    click("hospitalDecide","hospitals/decision")
                    for box in page.locator("input[name=opsHospital]").all(): box.check()
                    click("opsCreate","workflow/create")
                    for command in ("start","pause","resume","cancel","retry","aggregate"):
                        before=len(calls)
                        page.locator("[data-control="+command+"]").click()
                        page.wait_for_timeout(120)
                        check("admin / "+command, any(path=="workflow/control" and body.get("command")==command for path,body in calls[before:]))
                    page.locator("#opsFeedback").fill("Fixture feedback")
                    click("opsSendFeedback","workflow/feedback")
                    with page.expect_download(): click("opsExport","workflow/export")
                    for box in page.locator("input[name=rosterHospital]").all(): box.check()
                    click("createRoster","hospitals/roster")
                    page.locator(".shell-nav a[href='#experimentHistory']").click()
                    for identity, endpoint in [("refreshSystem","snapshot"),("monitorRefresh","snapshot"),
                        ("loadLog","log"),("auditRun","audit"),("liveBlocks","blocks")]:
                        click(identity,endpoint)
                    page.locator(".block button").first.click()
                    check("admin / transaction inspection", bool(page.locator("#receipt").inner_text()))
                else:
                    state["registered"]=False
                    click("connect");click("challenge","hospitals/challenge");click("sign")
                    click("login","hospitals/login")
                    page.locator("#name").fill("Fixture Hospital")
                    page.locator("#code").fill("TEST_0")
                    click("apply","hospitals/register")
                    page.wait_for_function("!document.getElementById('clientWorkspace').hidden", timeout=12000)
                    click("refresh","hospitals/me")
                    page.locator("#samples").fill("4")
                    click("heartbeat","hospitals/heartbeat")
                    for identity,endpoint in [("clientPrepare","workflow/prepare-agent"),("clientSign",None),
                        ("clientAuthorize","workflow/authorize-agent"),("clientRefresh","workflow/me")]:
                        click(identity,endpoint)
                    page.locator("#clientNamespace").fill("fixture")
                    for identity,endpoint in [("clientConfigure","workflow/configure"),("clientJoin","workflow/participate"),
                        ("clientStop","workflow/participate"),("clientLog","workflow/log")]:
                        click(identity,endpoint)
                page.locator("#includeHistoricalModels").check()
                buffer=io.BytesIO();Image.new("RGB",(224,224),"gray").save(buffer,format="PNG")
                page.locator("#image").set_input_files({"name":"fixture.png","mimeType":"image/png","buffer":buffer.getvalue()})
                click("predict","predict")
                if role=="admin": click("verify","verify")
                # Missing campaigns must disable state-changing controls.
                workflow["campaigns"]=[]
                click("opsRefresh" if role=="admin" else "clientRefresh")
                page.wait_for_timeout(200)
                check(role+" / no-campaign controls disabled", page.locator("[data-control=start]" if role=="admin" else "#clientJoin").is_disabled())
                workflow["campaigns"]=[campaign]
                # Exercise every sidebar destination on desktop.
                for link in page.locator(".shell-nav a").all():
                    link.click()
                    check(role+" / navigation "+link.inner_text(),link.get_attribute("aria-current")=="location")
                page.locator(".menu-toggle").click()
                check(role+" / desktop collapse",page.locator(".menu-toggle").get_attribute("aria-expanded")=="false")
                page.locator(".menu-toggle").click()
                page.set_viewport_size({"width":390,"height":844})
                page.locator(".menu-toggle").click()
                check(role+" / mobile menu", page.locator(".menu-toggle").get_attribute("aria-expanded")=="true")
                page.locator(".shell-overlay").click(position={"x":350,"y":200})
                check(role+" / overlay closes menu",page.locator(".menu-toggle").get_attribute("aria-expanded")=="false")
                page.locator(".menu-toggle").click()
                page.keyboard.press("Escape")
                check(role+" / Escape closes menu", page.locator(".menu-toggle").get_attribute("aria-expanded")=="false")
                page.screenshot(path=str(ROOT/"multiseed_outputs"/(role+"_dashboard_browser.png")),full_page=True)
                click("adminLogout" if role=="admin" else "logout", None if role=="admin" else "hospitals/logout")
                context.close()
            check("No uncaught JavaScript errors",not result["errors"])
        finally:
            browser.close()
            (ROOT/"multiseed_outputs/dashboard_button_checks.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__ == "__main__":
    main()
