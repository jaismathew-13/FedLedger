"""Check dashboard encoding, JavaScript syntax, and served asset freshness."""
import json
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
NODE = ROOT / ".tools/node-v22.23.3-win-x64/node.exe"


def main():
    checks = []

    def check(name, passed):
        checks.append({"name": name, "passed": bool(passed)})

    for name, route in [
        ("admin_dashboard.html", "/admin"),
        ("hospital_dashboard.html", "/hospital"),
        ("portal_admin.js", "/assets/portal_admin.js"),
        ("portal_hospital.js", "/assets/portal_hospital.js"),
        ("dashboard_shell.js", "/assets/dashboard_shell.js"),
        ("current_chain_explorer.js", "/assets/current_chain_explorer.js"),
        ("dashboard_shell.css", "/assets/dashboard_shell.css"),
    ]:
        raw = (ROOT / name).read_bytes()
        text = raw.decode("utf-8", errors="strict")
        check(name + ": no corrupted encoding markers",
              not any(c in text for c in ["\u00c3", "\u00c2", "\ufffd", "\u00e2"]))
        check(name + ": no question-mark separators",
              not re.search(r"""['"] \? | \? (?:Accepted|Rejected|Aggregation|Hospital|chain ID|latest block)""", text))
        scripts = [text] if name.endswith(".js") else re.findall(
            r"<script>(.*?)</script>", text, re.S)
        for index, script in enumerate(scripts):
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "check.js"
                path.write_text(script, encoding="utf-8")
                result = subprocess.run([str(NODE), "--check", str(path)],
                                        capture_output=True, text=True)
                check(f"{name}: script {index} syntax", result.returncode == 0)
                if result.returncode:
                    print(result.stderr)
        try:
            with urlopen("http://127.0.0.1:8765" + route, timeout=10) as response:
                check(name + ": live response UTF-8",
                      response.headers.get_content_charset() == "utf-8")
                check(name + ": live response matches updated file", response.read() == raw)
        except Exception as exc:
            check(name + ": live response " + str(exc), False)
    result = {"checked_utc": datetime.now(timezone.utc).isoformat(),
              "checks": checks, "passed": all(c["passed"] for c in checks),
              "scope": "Source encoding, JS syntax and HTTP assets; not visual browser testing"}
    (ROOT / "multiseed_outputs/dashboard_text_checks.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
