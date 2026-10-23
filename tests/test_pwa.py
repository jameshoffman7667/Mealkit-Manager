"""Release, PWA and packaging checks. File-based: no web framework needed."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
VERSION = (ROOT / "VERSION").read_text().strip()


def test_version_is_three_part():
    assert re.fullmatch(r"\d+\.\d+\.\d+", VERSION)


def test_manifest_fields_and_files():
    m = json.loads((STATIC / "manifest.webmanifest").read_text())
    for key in ("name", "short_name", "id", "start_url", "scope", "background_color", "theme_color", "description"):
        assert m.get(key), key
    assert m["display"] == "standalone" and m["start_url"] == "/" and m["scope"] == "/"
    sizes = {(i["sizes"], i.get("purpose", "any")) for i in m["icons"]}
    assert ("192x192", "any") in sizes and ("512x512", "any") in sizes and ("512x512", "maskable") in sizes
    forms = {s["form_factor"] for s in m["screenshots"]}
    assert forms == {"wide", "narrow"}
    for item in m["icons"] + m["screenshots"]:
        src = item["src"]
        path = STATIC / src.replace("/static/", "", 1) if src.startswith("/static/") else STATIC / src.lstrip("/")
        assert path.is_file(), src


def test_icon_sizes():
    from PIL import Image
    for name, size in (("icon-192.png", 192), ("icon-512.png", 512), ("icon-maskable-512.png", 512),
                       ("apple-touch-icon.png", 180)):
        assert Image.open(STATIC / "icons" / name).size == (size, size), name
    assert Image.open(STATIC / "screenshots" / "wide.png").size == (1280, 720)
    assert Image.open(STATIC / "screenshots" / "narrow.png").size == (540, 960)


def test_service_worker_version_matches_and_never_caches_api():
    sw = (STATIC / "sw.js").read_text()
    assert f'const VERSION = "{VERSION}"' in sw
    assert 'const CACHE = "mealkit-manager-v" + VERSION' in sw
    shell = re.search(r"const SHELL = \[(.*?)\];", sw, re.S).group(1)
    assert "/api/" not in shell and "export" not in shell and "login" not in shell
    assert "event.respondWith(fetch(req).catch" in sw        # navigations: network first, never cached
    assert "skipWaiting()" in sw and 'event.data === "SKIP_WAITING"' in sw
    install = sw[sw.index('addEventListener("install"'):sw.index('addEventListener("activate"')]
    assert "skipWaiting" not in install.replace("No skipWaiting", "")   # no silent takeover while typing


def test_app_js_avoids_reload_on_first_install_and_inline_code():
    js = (STATIC / "app.js").read_text()
    assert "hadController" in js and "if (hadController) window.location.reload()" in js
    for tpl in (ROOT / "app" / "templates").glob("*.html"):
        text = tpl.read_text()
        assert not re.search(r"\son\w+=\"", text), f"inline handler in {tpl.name}"
        assert "style=" not in text, f"inline style in {tpl.name}"
        assert not re.search(r"<script(?![^>]*\bsrc=)", text), f"inline script in {tpl.name}"


def test_base_template_has_pwa_tags():
    base = (ROOT / "app" / "templates" / "base.html").read_text()
    for needle in ('rel="manifest"', 'name="theme-color"', "apple-touch-icon", "viewport-fit=cover", 'name="viewport"'):
        assert needle in base


def test_changelog_entries_follow_the_release_format():
    text = (ROOT / "CHANGELOG.md").read_text()
    entries = re.findall(r"^## v(\S+) - .*\n\*\*Short:\*\* (.+)\n\*\*Long:\*\* (.+)$", text, re.M)
    assert entries and entries[0][0] == VERSION
    for ver, short, long_ in entries:
        assert 0 < len(short) <= 50, ver
        assert 0 < len(long_) <= 250, ver


def test_dockerfile_follows_port_and_standards():
    d = (ROOT / "Dockerfile").read_text()
    assert "# syntax" not in d
    assert "EXPOSE 8044" in d and "PORT=8044" in d
    assert "${PORT}" in d and "127.0.0.1" in d and "localhost" not in d
    assert "/healthz" in d and "tini" in d and "USER 1000:100" in d


def test_compose_is_pinned_and_container_port_equals_host_port():
    c = (ROOT / "deploy" / "compose.yaml").read_text()
    assert f"image: mybadreligon/mealkit-manager:{VERSION}" in c
    assert "latest" not in c and "build:" not in c
    assert "${PORT_HOST:-8044}:${PORT_HOST:-8044}" in c and "PORT=${PORT_HOST:-8044}" in c
    assert "$${PORT}/healthz" in c and "127.0.0.1" in c
    env = (ROOT / "deploy" / ".env.example").read_text()
    for name in ("PORT_HOST", "MEALKIT_SECRET_KEY", "MEALKIT_APP_PASSWORD", "SYNC_HOURS"):
        assert name in env


def test_release_notes_have_the_update_field():
    r = (ROOT / "deploy" / "RELEASE.md").read_text()
    assert f"# Release v{VERSION}" in r
    lines = [l for l in r.splitlines() if l.startswith("Update:")]
    assert lines in (["Update: now"], ["Update: later"])
    assert f"mybadreligon/mealkit-manager:{VERSION}" in r
    assert "Docker build:" in r and "Release commit:" in r


def test_release_workflow_is_the_standard_one():
    w = (ROOT / ".github" / "workflows" / "release.yml").read_text()
    assert 'tags: ["v*.*.*"]' in w and "branches" not in w
    assert "mybadreligon/mealkit-manager" in w and "type=raw,value=latest" in w
    assert "{{major}}.{{minor}}" in w and "linux/amd64" in w
    assert w.rindex("gh release create") > w.rindex("build-push-action")      # release is the last step
    assert not (ROOT / ".github" / "workflows" / "docker-publish.yml").exists()
    t = (ROOT / ".github" / "workflows" / "test.yml").read_text()
    assert "push: true" not in t and "docker/login" not in t


def test_schema_version_and_backup_on_upgrade(tmp_path, monkeypatch):
    import sqlite3
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app import db
    con = sqlite3.connect(tmp_path / "mealkit.db")
    con.executescript("CREATE TABLE accounts(id INTEGER PRIMARY KEY, service_id TEXT, nickname TEXT, email TEXT, "
                      "status TEXT, automation TEXT, note TEXT, created_at TEXT);"
                      "INSERT INTO accounts(service_id, nickname) VALUES ('hellofresh','old');")
    con.commit(); con.close()
    db.init()
    backups = list((tmp_path / "backups").glob("pre-migrate-1-to-2-*.db"))
    assert len(backups) == 1
    old = sqlite3.connect(backups[0])
    assert old.execute("SELECT nickname FROM accounts").fetchone()[0] == "old"
    old.close()
    con = sqlite3.connect(tmp_path / "mealkit.db")
    assert con.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == db.CURRENT_SCHEMA
    con.close()
    db.init()                                                                  # second start: no new backup
    assert len(list((tmp_path / "backups").glob("*.db"))) == 1
