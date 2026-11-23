"""Build a reproducible, allowlisted hosting ZIP; never include runtime data."""

import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def build():
    if not (ROOT / "dist/index.html").is_file():
        raise SystemExit("Build the website first: npm ci && npm run build")
    paths = [ROOT / name for name in (
        "loader.php", "LESSONS_LEARNED.md", "README.md", "RELEASE.json", "PLAN_EXECUTION.md", "docs/PHYSICAL_MODEL.md", "docs/ENGINEERING_CORE_07.md", "docs/REVIEW_WORKFLOW.md", "docs/CANONICAL_FLANGE_CATALOG.md", "docs/REMOTE_PROCESSING_CONTRACT.md", "requirements.txt", "scripts/run_updates.py", "scripts/enable_updates.py", "scripts/run_pipeline.py", "scripts/enable_pipeline.py", "scripts/build_functions_demo.py",
        "requirements-cpanel.txt", "passenger_wsgi.py", "docs/CPANEL.md", "docs/PROCESSING_PIPELINE.md", "docs/CAESAR_FORMATS.md", "docs/EXCEL_OUTPUT.md", "docs/LOGGING.md", "docs/ADMIN_RECOVERY.md", "docs/GITHUB_AND_SERVERLESS.md", "scripts/check_host.py", "scripts/configure_cpanel.py", "scripts/reset_admin.py",
    )]
    for directory in ("services", "packages"):
        paths.extend((ROOT / directory).rglob("*.py"))
    paths.append(ROOT / 'serverless/digitalocean/project.yml')
    paths.extend((ROOT / 'serverless/digitalocean/function').glob('*.py'))
    paths.extend(p for p in (ROOT / "dist").rglob("*") if p.is_file())
    contents = {}
    for path in sorted(paths):
        if path.is_symlink():
            raise SystemExit(f"Refusing symlink: {path}")
        contents[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    contents["public/.gitkeep"] = b""
    contents["MANIFEST.json"] = (json.dumps({
        "format": 1,
        "purpose": "cPanel Python/Passenger private pilot; not PHP-only hosting",
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()},
    }, indent=2) + "\n").encode()
    output = ROOT / "downloads/caesar-cpanel.zip"
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(contents.items()):
            info = zipfile.ZipInfo("caesar-system/" + name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(f"{digest}  {output.name}\n")
    print(f"Built {output.relative_to(ROOT)} ({output.stat().st_size:,} bytes); SHA-256 {digest}")


if __name__ == "__main__":
    build()
