"""The Windows installer: built and smoke-tested in release.yml, published
beside the .zip, and described in the release notes.

Owner ruling (2026-11-07): "I want free windows and leave Mac as is." The
installer is built free on the Windows runner, unsigned, per-user.
These tests pin the parts that would otherwise drop out silently: a workflow
edit that stops building or publishing the installer, an AppId change that
makes the next version install BESIDE the old one, an uninstall rule that
reaches into the user's data, or release notes that still say "extract it".
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISS = ROOT / "build" / "led_raster_designer.iss"
RELEASE_YML = ROOT / ".github" / "workflows" / "release.yml"

sys.path.insert(0, str(ROOT / "scripts"))
import generate_release_notes as gen  # noqa: E402

# NEVER change this. Setup finds the installed copy by it: a new AppId
# means the next version installs a second copy and a second Settings > Apps
# entry instead of upgrading.
APP_ID = "7D7BC445-209D-4629-A5D7-1C0B7EDC0C94"


def _iss():
    return ISS.read_text(encoding="utf-8")


def _section(text, name):
    m = re.search(r"^\[" + re.escape(name) + r"\]\s*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
    assert m, f"[{name}] missing from {ISS.name}"
    return [l.strip() for l in m.group(1).splitlines()
            if l.strip() and not l.strip().startswith(";")]


def _setup_value(key):
    for line in _section(_iss(), "Setup"):
        k, sep, v = line.partition("=")
        if sep and k.strip().lower() == key.lower():
            return v.strip()
    return None


def _yml():
    return RELEASE_YML.read_text(encoding="utf-8")


def _job(name):
    """The text of one job in release.yml (two-space indented key)."""
    text = _yml()
    m = re.search(r"^  " + re.escape(name) + r":\n(.*?)(?=^  [\w-]+:\n|\Z)", text, re.M | re.S)
    assert m, f"job {name} missing from release.yml"
    return m.group(1)


# ── the installer script ────────────────────────────────────────────────

def test_app_id_is_stable():
    assert _setup_value("AppId") == "{{" + APP_ID + "}"


def test_installs_per_user_without_admin():
    assert _setup_value("PrivilegesRequired") == "lowest"
    # {autopf} is %LOCALAPPDATA%\Programs at lowest privileges
    assert _setup_value("DefaultDirName") == r"{autopf}\{#AppName}"
    assert _setup_value("PrivilegesRequiredOverridesAllowed") is None


def test_version_comes_from_the_build_and_names_the_file():
    assert _setup_value("AppVersion") == "{#AppVersion}"
    assert _setup_value("VersionInfoVersion") == "{#AppNumericVersion}"
    assert _setup_value("OutputBaseFilename") == "led_raster_designer_v{#AppVersion}_windows_setup"


def test_shortcuts_icon_and_uninstall_entry():
    icons = _section(_iss(), "Icons")
    assert any(l.startswith('Name: "{autoprograms}\\{#AppName}"') for l in icons), icons
    assert any(l.startswith('Name: "{autodesktop}\\{#AppName}"') and "Tasks: desktopicon" in l
               for l in icons), icons
    assert any(l.startswith('Name: "desktopicon"') for l in _section(_iss(), "Tasks"))
    assert _setup_value("SetupIconFile") == r"..\src\icon.ico"
    # an Inno path uses backslashes; read it the same way on every OS
    assert (ISS.parent / _setup_value("SetupIconFile").replace("\\", "/")).resolve().is_file()
    assert _setup_value("UninstallDisplayIcon") == r"{app}\{#AppExeName}"


def test_install_and_uninstall_only_touch_the_install_folder():
    """User data (logs, presets, layouts, settings) lives outside {app}, and
    no delete rule may reach past {app}."""
    for section in ("InstallDelete", "UninstallDelete"):
        for line in _section(_iss(), section):
            m = re.search(r'Name: "([^"]+)"', line)
            assert m, line
            assert m.group(1) == "{app}" or m.group(1).startswith("{app}\\"), (
                f"[{section}] deletes outside the install folder: {line}")


def test_runtime_files_beside_the_exe_are_handled():
    """launcher_window.py writes these two beside the exe. The build leaves
    the CI copies out, and the uninstaller removes them so the folder goes."""
    launcher = (ROOT / "src" / "launcher_window.py").read_text(encoding="utf-8")
    assert "_MOTW_SENTINEL = '.lrd-unblocked'" in launcher
    assert "'launcher_crash.log'" in launcher
    files = " ".join(_section(_iss(), "Files"))
    assert 'Excludes: ".lrd-unblocked,launcher_crash.log"' in files
    undel = _section(_iss(), "UninstallDelete")
    assert 'Type: files; Name: "{app}\\.lrd-unblocked"' in undel
    assert 'Type: files; Name: "{app}\\launcher_crash.log"' in undel


def test_a_running_copy_is_closed_first():
    text = _iss()
    assert _setup_value("CloseApplications") == "force"
    assert "function PrepareToInstall(" in text
    assert "function InitializeUninstall(" in text


def test_user_data_stays_outside_the_install_folder():
    """If the app ever starts writing next to itself, the per-user install
    and the uninstaller both need another look."""
    app = (ROOT / "src" / "app.py").read_text(encoding="utf-8")
    assert "base = os.environ.get('LOCALAPPDATA')" in app
    assert "os.path.join(base, APP_NAME, 'presets')" in app
    settings = (ROOT / "src" / "launcher_settings.py").read_text(encoding="utf-8")
    assert "os.environ.get('APPDATA'" in settings


# ── the release workflow ────────────────────────────────────────────────

def test_windows_job_builds_and_smoke_tests_the_installer():
    job = _job("build-windows")
    assert "build\\led_raster_designer.iss" in job
    assert "ISCC.exe" in job
    assert "src\\VERSION.txt" in job, "the installer version must come from VERSION.txt"
    smoke = job[job.index("Smoke test the installer"):]
    for needle in ("/VERYSILENT", "Start-App", "$startLnk", "$uninstKey",
                   "UninstallString", "preset kept", "settings kept", "logs kept",
                   "setup closed the running copy", "uninstall closed the running copy"):
        assert needle in smoke, f"installer smoke test lost: {needle}"
    assert "{" + APP_ID + "}" in smoke, "smoke test checks a different AppId"


def test_installer_is_uploaded_checksummed_and_published():
    assert "led_raster_designer_v*_windows_setup.exe" in _job("build-windows")
    release = _job("release")
    sums = next(l for l in release.splitlines() if "sha256sum" in l)
    assert "windows-build/*_windows_setup.exe" in sums
    assert "artifacts/windows-build/*_windows_setup.exe" in release


def test_only_a_tag_publishes():
    """workflow_dispatch builds the installer for testing; it must never be
    able to create a release."""
    assert re.search(r"^  workflow_dispatch:", _yml(), re.M)
    assert "    if: startsWith(github.ref, 'refs/tags/v')\n" in _job("release")


# ── the release notes ───────────────────────────────────────────────────

def _dash_or_spelling_hits(text):
    hits = []
    for bad in ("—", "–", " - "):
        if bad in text:
            hits.append(repr(bad))
    for word in ("colour", "behaviour", "organise", "catalogue", "licence"):
        if word in text.lower():
            hits.append(word)
    return hits


def test_install_notes_point_at_the_setup_file():
    windows = gen.INSTALL[gen.INSTALL.index("**Windows:**"):]
    assert "_windows_setup.exe" in windows
    assert "More info, then Run anyway" in windows
    assert "extract it" not in windows
    assert not _dash_or_spelling_hits(gen.INSTALL), _dash_or_spelling_hits(gen.INSTALL)


def test_install_notes_mention_the_zip_only_while_it_ships():
    """The .zip ships beside the installer for one release. When release.yml
    stops publishing it, the notes must stop offering it, and vice versa."""
    ships_zip = "artifacts/windows-build/*.zip" in _job("release")
    offers_zip = "is still attached to this release" in gen.INSTALL
    assert ships_zip == offers_zip
