"""Android (TWA) build checks, spec v1.11 section 15. Ported from MaintEnhance backend/test/android.test.js.
Each assertion guards a bug that cost a release there. The web test at the end needs FastAPI (CI only)."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
TWA = json.loads((ROOT / "twa-manifest.json").read_text())
WORKFLOW = (ROOT / ".github" / "workflows" / "release.yml").read_text()


def version_code(version):
    """Same rule as scripts/android-version.js: MAJOR*100000000 + MINOR*10000 + PATCH."""
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(version or ""))
    if not m:
        raise ValueError(f"'{version}' is not MAJOR.MINOR.PATCH")
    major, minor, patch = map(int, m.groups())
    if minor > 9999 or patch > 9999:
        raise ValueError("MINOR and PATCH must each be 9999 or less")
    if major > 20:
        raise ValueError("MAJOR must be 20 or less")
    return major * 100000000 + minor * 10000 + patch


def test_version_code_rule_and_limits():
    assert version_code("2.11.0") == 200110000
    assert version_code("2.11.1") == 200110001
    assert version_code("0.1.0") == 10000
    assert version_code("0.5.0") == 50000
    assert version_code("20.9999.9999") == 2000000000 + 99990000 + 9999
    assert version_code("2.12.0") > version_code("2.11.9999")
    for bad in ("2.10000.0", "2.0.10000", "21.0.0", "2.1"):
        with pytest.raises(ValueError):
            version_code(bad)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_python_and_node_version_code_agree():
    for v in ("0.4.2", "0.5.0", "1.0.0", "2.11.5", "20.9999.9999"):
        out = subprocess.run(["node", str(ROOT / "scripts" / "android-version.js"), v],
                             capture_output=True, text=True, check=True).stdout.strip()
        assert int(out) == version_code(v), v
    for bad in ("2.10000.0", "21.0.0", "2.1"):
        r = subprocess.run(["node", str(ROOT / "scripts" / "android-version.js"), bad], capture_output=True, text=True)
        assert r.returncode == 1 and r.stderr.strip(), bad


def test_release_version_fits_the_android_rule():
    version_code((ROOT / "VERSION").read_text().strip())


def test_twa_manifest_required_fields():
    assert TWA["packageId"] == "ca.hoffmanhouse.mealkit"
    assert re.fullmatch(r"ca\.hoffmanhouse\.[a-z0-9]+", TWA["packageId"]), "lowercase letters and digits only"
    assert TWA["host"] == "mealkit.hoffmanhouse.ca" and TWA["host"].endswith(".hoffmanhouse.ca")
    assert TWA["display"] == "standalone" and TWA["fallbackType"] == "customtabs" and TWA["startUrl"] == "/"
    assert TWA["iconUrl"].startswith("https://" + TWA["host"] + "/") and "maskable" in TWA["maskableIconUrl"]
    assert TWA["signingKey"]["alias"] == "mealkit"
    text = json.dumps(TWA)
    assert not re.search(r"password", text, re.I), "no passwords in twa-manifest.json"
    assert "<" not in text, "no <PLACEHOLDER> left in twa-manifest.json"


def test_twa_uses_bubblewrap_version_fields():
    assert isinstance(TWA["appVersion"], str) and isinstance(TWA["appVersionCode"], int)
    assert "appVersionName" not in TWA


def test_min_sdk_is_at_least_24():
    assert TWA["minSdkVersion"] >= 24


def test_site_settings_shortcut_stays_true():
    # The browser helper library toggles ManageDataLauncherActivity at start and crashes without it.
    assert TWA["enableSiteSettingsShortcut"] is True


def test_notifications_only_if_the_app_uses_web_push():
    uses_push = any(re.search(r"pushManager|PushSubscription|showNotification|vapid", p.read_text(), re.I)
                    for p in list((ROOT / "app").rglob("*.py")) + list(STATIC.glob("*.js")))
    assert TWA["enableNotifications"] is uses_push


def test_manifest_colours_match_the_web_manifest():
    web = json.loads((STATIC / "manifest.webmanifest").read_text())
    assert TWA["themeColor"].lower() == web["theme_color"].lower()
    assert TWA["backgroundColor"].lower() == web["background_color"].lower()


def test_twa_icons_are_the_ones_the_web_manifest_serves():
    web = json.loads((STATIC / "manifest.webmanifest").read_text())
    srcs = {i["src"] for i in web["icons"]}
    assert TWA["iconUrl"].split(TWA["host"], 1)[1] in srcs
    assert TWA["maskableIconUrl"].split(TWA["host"], 1)[1] in srcs


def test_assetlinks_file():
    j = json.loads((STATIC / "assetlinks.json").read_text())
    assert j[0]["target"]["package_name"] == TWA["packageId"]
    assert j[0]["target"]["namespace"] == "android_app"
    assert "delegate_permission/common.handle_all_urls" in j[0]["relation"]
    fps = j[0]["target"]["sha256_cert_fingerprints"]
    assert fps and all(re.fullmatch(r"([0-9A-F]{2}:){31}[0-9A-F]{2}", f) for f in fps), "real SHA-256 fingerprint"


def test_release_workflow_android_job():
    assert re.search(r"\n  plan:\n    if: github\.event_name != 'workflow_dispatch'", WORKFLOW)
    assert re.search(r"\n  image:\n(?:.*\n)*?    needs: \[plan, test\]", WORKFLOW)
    assert re.search(r"\n  image:\n(?:.*\n)*?    if: github\.event_name != 'workflow_dispatch'", WORKFLOW)
    assert re.search(r"\n  android:\n    needs: \[plan, image\]", WORKFLOW)
    assert "twa-manifest.json" in WORKFLOW and "gh release upload" in WORKFLOW
    assert "workflow_dispatch:" in WORKFLOW and "overwrite" in WORKFLOW
    assert "APP: mealkit-manager" in WORKFLOW and "ASSETLINKS_PATH: app/static/assetlinks.json" in WORKFLOW
    assert "androguard" in WORKFLOW and 'grep -qi "$FP" "$ASSETLINKS_PATH"' in WORKFLOW
    assert "needs.prepare" not in WORKFLOW


def test_existing_release_logic_is_unchanged():
    assert 'tags: ["v*.*.*"]' in WORKFLOW and "branches: [main]" in WORKFLOW
    assert "paths:" not in WORKFLOW.split("jobs:")[0]         # no paths filter: plan decides from VERSION
    assert 'gh release create "v$VERSION" --target "$GITHUB_SHA"' in WORKFLOW
    assert "group: release-${{ needs.plan.outputs.version }}" in WORKFLOW


def test_no_secrets_or_keystore_in_the_repo():
    assert not list(ROOT.glob("*.keystore")) and not list(ROOT.glob("*.jks")) and not list(ROOT.glob("*.apk"))
    ignore = (ROOT / ".gitignore").read_text()
    assert "*.keystore" in ignore and "*.apk" in ignore


def test_assetlinks_route_is_public_json_without_redirect(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from app import main as main_mod
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("APP_PASSWORD", "s3cret")         # still public with a password set
    with TestClient(main_mod.app) as c:
        r = c.get("/.well-known/assetlinks.json", follow_redirects=False)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/json")
        j = r.json()
        assert j[0]["target"]["package_name"] == TWA["packageId"]
        assert j[0]["target"]["sha256_cert_fingerprints"] == json.loads((STATIC / "assetlinks.json").read_text())[0]["target"]["sha256_cert_fingerprints"]
