"""Build preflight and isolated frozen smoke test; standard library + build tools."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import runpy
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
VERSION_DATA = runpy.run_path(str(ROOT / "physalix/_version.py"))
VERSION = VERSION_DATA["__version__"]
VERSION_INFO = VERSION_DATA["__version_info__"]


def adjacent_version(parts, direction):
    values = list(parts)
    for index in range(len(values) - 1, -1, -1):
        if direction > 0 and values[index] < 65535:
            values[index] += 1
            values[index + 1:] = [0] * (len(values) - index - 1)
            return ".".join(map(str, values))
        if direction < 0 and values[index] > 0:
            values[index] -= 1
            values[index + 1:] = [0] * (len(values) - index - 1)
            return ".".join(map(str, values))
    raise AssertionError("Current version has no valid adjacent version")


def avrdude_startup(executable: Path, config: Path) -> str:
    assert executable.is_file(), f"Missing AVRDUDE executable: {executable}"
    assert config.is_file(), f"Missing AVRDUDE configuration: {config}"
    result = subprocess.run([str(executable), "-C", str(config), "-?"],
                            cwd=executable.parent,
                            timeout=15, capture_output=True, text=True)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "avrdude version 8.1" in output.lower(), output
    return output


def environment():
    assert sys.platform == "win32" and platform.machine().lower() in ("amd64", "x86_64")
    assert sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32, "Use CPython 3.12 x64"
    assert re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-dev)?", VERSION)
    assert len(VERSION_INFO) == 3 and all(type(x) is int and 0 <= x <= 65535 for x in VERSION_INFO)
    for line in (ROOT / "packaging/requirements-build.txt").read_text().splitlines():
        if line and not line.startswith("#"):
            name, expected = line.split("==")
            actual = importlib.metadata.version(name)
            assert actual == expected, f"{name}: {actual} != {expected}; install packaging/requirements-build.txt"
    subprocess.run([sys.executable, "-m", "pip", "check"], check=True)
    from physalix.release_notes import load_release_notes
    from physalix.updates import Manifest, is_newer
    assert not is_newer(adjacent_version(VERSION_INFO, -1))
    assert not is_newer(VERSION)
    assert is_newer(adjacent_version(VERSION_INFO, 1))
    load_release_notes(require_current=True, current_version=VERSION)
    manifest = Manifest.parse(json.dumps({
        "version": VERSION,
        "installer_url": (
            f"https://github.com/jeansittler/Physalix/releases/download/"
            f"v{VERSION}/Physalyx-Setup-{VERSION}.exe"
        ),
        "sha256": "0" * 64,
        "notes": "Précontrôle de release",
        "mandatory": False,
    }))
    assert manifest.version == VERSION
    print(f"Environment OK: Python {platform.python_version()}, Physalyx {VERSION}")


def bundle(directory):
    from PyInstaller.archive.readers import CArchiveReader
    import pefile
    directory = directory.resolve()
    exe = directory / "Physalyx.exe"
    pe = pefile.PE(str(exe))
    assert pe.FILE_HEADER.Machine == 0x8664
    assert pe.OPTIONAL_HEADER.Subsystem == 2, "GUI executable expected"
    fixed = pe.VS_FIXEDFILEINFO[0]
    major, minor, patch = VERSION_INFO
    assert (fixed.FileVersionMS, fixed.FileVersionLS) == ((major << 16) | minor, patch << 16)
    pe.close()
    modules = CArchiveReader(str(exe)).open_embedded_archive("PYZ.pyz").toc
    assert "physalix.app" in modules and "numpy" in modules and "scipy" in modules
    assert all(name in modules for name in ("physalix.updates", "physalix.ui.updates", "urllib.request", "ssl"))
    assert not any(n.startswith(("physlab", "physalyx", "tests.")) for n in modules)
    forbidden = {".venv", ".git", ".github", ".pytest_cache", "__pycache__", "tests", "build", "dist"}
    for path in directory.rglob("*"):
        assert not forbidden.intersection(path.relative_to(directory).parts), path
    for source in (ROOT / "physalix/ui/resources").rglob("*"):
        if source.is_file():
            target = directory / "_internal" / source.relative_to(ROOT)
            assert target.read_bytes() == source.read_bytes(), target
    firmware_source = ROOT / "physalix/resources/firmware"
    for source in firmware_source.rglob("*"):
        if source.is_file():
            target = directory / "_internal" / source.relative_to(ROOT)
            assert target.read_bytes() == source.read_bytes(), target
    from physalix.firmware_resources import load_nano_resources, load_uno_resources
    firmware = load_uno_resources(
        directory / "_internal/physalix/resources/firmware/uno")
    avrdude_startup(firmware.uploader_executable, firmware.uploader_config)
    nano = load_nano_resources(
        directory / "_internal/physalix/resources/firmware/nano-spectro",
        directory / "_internal/physalix/resources/firmware/uno",
    )
    assert nano.manifest.firmware_version == "1.0.0"
    assert nano.manifest.protocol_version == 1
    assert nano.manifest.required_capabilities == 0x1F
    assert nano.uploader_executable == firmware.uploader_executable
    assert nano.uploader_config == firmware.uploader_config
    for name in ("python312.dll", "VCRUNTIME140.dll", "VCRUNTIME140_1.dll", "MSVCP140.dll"):
        assert list(directory.rglob(name)), f"Missing runtime: {name}"
    assert list(directory.rglob("qwindows.dll")), "Windows Qt plugin missing"
    for notice in ("LICENSE", "THIRD_PARTY_NOTICES.md", "LISEZ-MOI.txt"):
        assert (directory / "_internal" / notice).is_file(), f"Missing distribution notice: {notice}"
    for notice in ("README.md", "components.json"):
        target = directory / "_internal" / "third_party" / notice
        assert target.is_file(), f"Missing third-party compliance file: {target}"
    for notice in ("AVRDUDE-8.1-GPL-2.0-or-later.txt", "AVRDUDE-8.1-AUTHORS.txt"):
        target = directory / "_internal" / "third_party" / "licenses" / notice
        assert target.is_file(), f"Missing AVRDUDE notice: {target}"
    assert list((directory / "_internal" / "third_party" / "licenses").glob("*.txt")), \
        "Missing third-party license texts"
    env = os.environ.copy()
    for key in list(env):
        if key.upper().startswith(("PYTHON", "QT_", "PYSIDE", "VIRTUAL_ENV", "CONDA")):
            del env[key]
    windows = os.environ["SystemRoot"]
    env["PATH"] = os.pathsep.join([str(Path(windows) / "System32"), windows])
    temporary_root = ROOT / "artifacts"
    temporary_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="Physalyx external cwd ", dir=temporary_root) as temporary:
        env["TMP"] = temporary
        env["TEMP"] = temporary
        report = Path(temporary) / "report.json"
        result = subprocess.run([str(exe), "--distribution-check", str(report)], cwd=temporary,
                                env=env, timeout=90, capture_output=True)
        data = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {}
        data["exit_code"] = result.returncode
        data["stderr"] = result.stderr.decode(errors="replace")
        (ROOT / "artifacts/distribution-check.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
        assert result.returncode == 0 and data.get("ok") and data.get("frozen"), data
        assert data["version"] == VERSION and data["platform"] == "windows", data
    files = [{"path": str(p.relative_to(directory)), "size": p.stat().st_size,
              "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
             for p in sorted(directory.rglob("*")) if p.is_file()]
    manifest = {"version": VERSION, "python": platform.python_version(), "files": files,
                "bytes": sum(f["size"] for f in files)}
    (ROOT / "artifacts/bundle-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Frozen check OK: {len(files)} files, {manifest['bytes'] / 1024**2:.1f} MiB")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["environment", "bundle"])
    parser.add_argument("directory", nargs="?", type=Path, default=ROOT / "dist/Physalyx")
    args = parser.parse_args()
    environment() if args.action == "environment" else bundle(args.directory)
