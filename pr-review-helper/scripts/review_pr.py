#!/usr/bin/env python3
"""Review Dify plugin PRs with local pre-checks and README language gating."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

DEFAULT_REPO = "langgenius/dify-plugins"
DEFAULT_MARKETPLACE_BASE_URL = "https://marketplace.dify.ai"
DEFAULT_MARKETPLACE_TOKEN = "placeholder"
DEFAULT_README_MAX_CJK = 0
DEFAULT_PR_CONTENT_MAX_CJK = 0
README_MULTILINGUAL_DOC_URL = (
    "https://docs.dify.ai/en/develop-plugin/features-and-specs/plugin-types/"
    "multilingual-readme#multilingual-readme"
)
DEFAULT_ALLOWED_PR_CJK_SNIPPETS = (
    "【中文用户 & Non English User】请使用英语提交，否则会被关闭 ：）",
)
MIN_DIFY_PLUGIN_VERSION = "0.5.0"
MIN_PYTHON = (3, 11)

DEFAULT_ICON = """<svg width="100" height="100" xmlns="http://www.w3.org/2000/svg">
  <path d="M20 20 V80 M20 20 H60 Q80 20 80 40 T60 60 H20"
        fill="none"
        stroke="black"
        stroke-width="5"/>
</svg>"""


class CheckFailed(RuntimeError):
    """Raised when a check fails."""


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def run_cmd(
    cmd: List[str],
    *,
    cwd: Path | None = None,
    env: Dict[str, str] | None = None,
    timeout: int | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    printable = " ".join(shlex_quote(x) for x in cmd)
    print(f"$ {printable}")
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
    )
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)
    if check and result.returncode != 0:
        raise CheckFailed(
            f"Command failed ({result.returncode}): {printable}\n{result.stderr.strip()}"
        )
    return result


def shlex_quote(value: str) -> str:
    if not value:
        return "''"
    if re.fullmatch(r"[A-Za-z0-9_\-./:=]+", value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"


def ensure_command_exists(command: str) -> None:
    if shutil.which(command):
        return
    raise CheckFailed(f"Missing required command: {command}")


def detect_python_cmd(explicit: str | None = None) -> str:
    if explicit:
        if not shutil.which(explicit):
            raise CheckFailed(f"Configured Python command not found: {explicit}")
        return explicit

    for candidate in ("python3.12", "python3.11", "python3"):
        if not shutil.which(candidate):
            continue
        result = run_cmd([candidate, "-c", "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"])
        raw = result.stdout.strip()
        try:
            major, minor = (int(part) for part in raw.split(".", 1))
        except Exception:
            continue
        if (major, minor) >= MIN_PYTHON:
            return candidate

    required = ".".join(str(part) for part in MIN_PYTHON)
    raise CheckFailed(f"Unable to find Python >= {required}. Tried python3.12/python3.11/python3.")


def daemon_pattern_for_host() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "linux":
        arch = "arm64" if machine in {"arm64", "aarch64"} else "amd64"
        return f"dify-plugin-linux-{arch}"
    if system == "darwin":
        arch = "arm64" if machine in {"arm64", "aarch64"} else "amd64"
        return f"dify-plugin-darwin-{arch}"
    if system.startswith("win"):
        arch = "arm64" if machine in {"arm64", "aarch64"} else "amd64"
        return f"dify-plugin-windows-{arch}.exe"

    raise CheckFailed(f"Unsupported host platform for plugin daemon: system={system} arch={machine}")


def failure_result(name: str, message: str) -> CheckResult:
    return CheckResult(name=name, ok=False, detail=message)


def gh_json(pr_ref: str, repo: str, fields: str) -> dict:
    result = run_cmd(
        [
            "gh",
            "pr",
            "view",
            pr_ref,
            "-R",
            repo,
            "--json",
            fields,
        ]
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise CheckFailed(f"Failed to parse gh JSON output: {exc}") from exc


def checkout_pr(pr_ref: str, repo: str, workdir: Path) -> None:
    run_cmd(["gh", "pr", "checkout", pr_ref, "-R", repo], cwd=workdir)


def current_branch(workdir: Path) -> str:
    return run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=workdir).stdout.strip()


def delete_local_branch(workdir: Path, branch: str) -> None:
    if not branch or branch == "HEAD":
        return
    run_cmd(["git", "branch", "-D", branch], cwd=workdir, check=False)


def parse_manifest(path: Path) -> dict:
    data: Dict[str, str] = {}
    if not path.exists():
        raise CheckFailed(f"manifest.yaml not found: {path}")

    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0].isspace():
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith(('"', "'")) and value.endswith(('"', "'")) and len(value) >= 2:
            value = value[1:-1]
        data[key] = value
    return data


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", "", text)


def check_manifest_author(manifest: dict) -> CheckResult:
    author = (manifest.get("author") or "").lower()
    if "langgenius" in author or "dify" in author:
        return CheckResult(
            name="Manifest author",
            ok=False,
            detail="manifest.yaml author must not contain 'langgenius' or 'dify'.",
        )
    return CheckResult("Manifest author", True, "author is valid.")


def check_icon(plugin_dir: Path, manifest: dict) -> CheckResult:
    icon_name = (manifest.get("icon") or "").strip()
    if not icon_name:
        return CheckResult("Icon validation", False, "manifest.yaml icon field is empty.")

    icon_path = plugin_dir / "_assets" / icon_name
    if not icon_path.exists():
        return CheckResult(
            "Icon validation",
            False,
            f"icon file not found: _assets/{icon_name}",
        )

    icon_content = icon_path.read_text(encoding="utf-8", errors="ignore")
    if "DIFY_MARKETPLACE_TEMPLATE_ICON_DO_NOT_USE" in icon_content:
        return CheckResult(
            "Icon validation",
            False,
            "icon contains template placeholder marker.",
        )

    if normalize_ws(icon_content) == normalize_ws(DEFAULT_ICON):
        return CheckResult(
            "Icon validation",
            False,
            "icon matches default template icon and must be customized.",
        )

    return CheckResult("Icon validation", True, f"icon exists: _assets/{icon_name}")


def check_version_availability(
    base_url: str,
    manifest: dict,
) -> CheckResult:
    author = (manifest.get("author") or "").strip()
    name = (manifest.get("name") or "").strip()
    version = (manifest.get("version") or "").strip()
    if not author or not name or not version:
        return CheckResult(
            "Version check",
            False,
            "manifest.yaml must include author, name, and version.",
        )

    url = (
        f"{base_url.rstrip('/')}/api/v1/plugins/"
        f"{urllib.parse.quote(author)}/{urllib.parse.quote(name)}/{urllib.parse.quote(version)}"
    )

    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            code = resp.getcode()
            body = resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as exc:
        if exc.code != 200:
            return CheckResult("Version check", True, f"version {version} is available.")
        code = exc.code
        body = exc.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        return CheckResult(
            "Version check",
            False,
            f"failed to query marketplace API: {exc}",
        )

    if code == 200:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {}
        if str(payload.get("code")) == "0":
            return CheckResult(
                "Version check",
                False,
                f"version {version} already exists in marketplace.",
            )

    return CheckResult("Version check", True, f"version {version} is available.")


def build_toolkit_env(venv_dir: Path, python_cmd: str) -> Tuple[Path, Path]:
    run_cmd([python_cmd, "-m", "venv", str(venv_dir)])
    pip = venv_dir / "bin" / "pip"
    python = venv_dir / "bin" / "python"
    run_cmd([str(pip), "install", "--upgrade", "pip"])
    run_cmd([str(pip), "install", "requests", "packaging"])
    return python, pip


def install_plugin_deps(pip: Path, plugin_dir: Path) -> CheckResult:
    req_file = plugin_dir / "requirements.txt"
    if not req_file.exists():
        return CheckResult("Dependency install", True, "requirements.txt not found; skipped.")

    run_cmd([str(pip), "install", "-r", str(req_file)], timeout=600)
    return CheckResult("Dependency install", True, "requirements installed successfully.")


def detect_dify_plugin_version(pip: Path) -> str | None:
    result = run_cmd([str(pip), "list", "--format", "json"])
    try:
        packages = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    for package in packages:
        name = str(package.get("name", "")).lower().replace("-", "_")
        if name == "dify_plugin":
            return str(package.get("version", ""))
    return None


def version_is_at_least(python: Path, version: str, minimum: str) -> bool:
    py_code = (
        "from packaging.version import Version\n"
        "import sys\n"
        "sys.exit(0 if Version(sys.argv[1]) >= Version(sys.argv[2]) else 1)"
    )
    probe = subprocess.run(
        [str(python), "-c", py_code, version, minimum],
        capture_output=True,
        text=True,
    )
    return probe.returncode == 0


def version_is_greater_than(python: Path, version: str, baseline: str) -> bool:
    py_code = (
        "from packaging.version import Version\n"
        "import sys\n"
        "sys.exit(0 if Version(sys.argv[1]) > Version(sys.argv[2]) else 1)"
    )
    probe = subprocess.run(
        [str(python), "-c", py_code, version, baseline],
        capture_output=True,
        text=True,
    )
    return probe.returncode == 0


def check_dify_plugin_version(pip: Path, minimum: str) -> CheckResult:
    version = detect_dify_plugin_version(pip)
    if version is None:
        return CheckResult(
            "dify_plugin version",
            False,
            f"dify_plugin must be installed and >= {minimum}, but it was not found.",
        )

    if not version_is_at_least(pip.parent / "python", version, minimum):
        return CheckResult(
            "dify_plugin version",
            False,
            f"dify_plugin version must be >= {minimum}; found {version}.",
        )

    return CheckResult(
        "dify_plugin version",
        True,
        f"dify_plugin version {version} satisfies >= {minimum}.",
    )


def configure_install_env(base_env: Dict[str, str], pip: Path) -> Dict[str, str]:
    env = dict(base_env)
    version = detect_dify_plugin_version(pip)
    if version is None:
        env["INSTALL_METHOD"] = "aws_lambda"
        env["AWS_LAMBDA_PORT"] = "8080"
        env["AWS_LAMBDA_HOST"] = "0.0.0.0"
        return env

    if version_is_greater_than(pip.parent / "python", version, "0.0.1b64"):
        env["INSTALL_METHOD"] = "serverless"
        env["SERVERLESS_PORT"] = "8080"
        env["SERVERLESS_HOST"] = "0.0.0.0"
    else:
        env["INSTALL_METHOD"] = "aws_lambda"
        env["AWS_LAMBDA_PORT"] = "8080"
        env["AWS_LAMBDA_HOST"] = "0.0.0.0"
    return env


def run_install_test(
    python: Path,
    pip: Path,
    toolkit_dir: Path,
    plugin_dir: Path,
) -> CheckResult:
    req_file = plugin_dir / "requirements.txt"
    if not req_file.exists():
        return CheckResult("Install test", True, "requirements.txt not found; skipped.")

    env = configure_install_env(os.environ, pip)
    venv_bin = str(pip.parent)
    env["VIRTUAL_ENV"] = str(pip.parent.parent)
    env["PATH"] = f"{venv_bin}:{env.get('PATH', '')}"
    run_cmd(
        [
            str(python),
            str(toolkit_dir / "validator" / "test-plugin-install.py"),
            "-d",
            str(plugin_dir),
        ],
        env=env,
        timeout=300,
    )
    return CheckResult("Install test", True, "plugin install test passed.")


def run_packaging_test(
    python: Path,
    toolkit_dir: Path,
    daemon_path: Path,
    plugin_dir: Path,
    base_url: str,
    token: str,
) -> CheckResult:
    run_cmd([str(daemon_path), "version"])
    run_cmd(
        [
            str(python),
            str(toolkit_dir / "uploader" / "upload-package.py"),
            "-d",
            str(plugin_dir),
            "-t",
            token,
            "--plugin-daemon-path",
            str(daemon_path),
            "-u",
            base_url,
            "-f",
            "--test",
        ],
        timeout=300,
    )
    return CheckResult("Packaging test", True, "packaging check passed.")


def strip_code_blocks(text: str) -> str:
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def normalize_for_snippet_match(text: str) -> str:
    """Normalize text to make snippet replacement robust to line breaks/spacing."""
    return re.sub(r"\s+", " ", text).strip()


def strip_self_checks_section(markdown: str) -> str:
    """
    Remove the "Self Checks" section from PR body before language checks.
    This applies to plugin repos where the template may include bilingual checklist text.
    """
    pattern = re.compile(
        r"(?ims)^#{1,6}\s*.*self\s*checks.*$\n.*?(?=^#{1,6}\s+|\Z)"
    )
    return re.sub(pattern, "", markdown)


def pr_content_language_result(
    pr_data: dict,
    max_cjk: int,
    allowed_snippets: List[str],
) -> CheckResult:
    title = str(pr_data.get("title") or "")
    body = strip_self_checks_section(str(pr_data.get("body") or ""))
    text = strip_code_blocks(f"{title}\n{body}")
    normalized = normalize_for_snippet_match(text)

    ignored = 0
    for snippet in allowed_snippets:
        if not snippet:
            continue
        normalized_snippet = normalize_for_snippet_match(snippet)
        if not normalized_snippet:
            continue
        count = normalized.count(normalized_snippet)
        if count:
            ignored += count * len(re.findall(r"[\u3400-\u4DBF\u4E00-\u9FFF]", normalized_snippet))
            normalized = normalized.replace(normalized_snippet, " ")

    cjk_matches = re.findall(r"[\u3400-\u4DBF\u4E00-\u9FFF]", normalized)
    cjk_count = len(cjk_matches)
    en_count = len(re.findall(r"[A-Za-z]", normalized))
    total = cjk_count + en_count
    ratio = (cjk_count / total) if total else 0.0

    detail = (
        "PR title/body CJK ratio="
        f"{ratio:.1%} (zh={cjk_count}, en={en_count}, ignored_zh={ignored}, allowed_zh<={max_cjk})"
    )
    if cjk_count > max_cjk:
        return CheckResult(
            "PR content language",
            False,
            detail + "; Chinese characters are not allowed in PR content except configured allowlist snippets.",
        )

    return CheckResult("PR content language", True, detail)


REQUIRED_FILES = ("manifest.yaml",)
EXPECTED_FILES = ("README.md", "PRIVACY.md")
PRIVACY_DOC_URL = (
    "https://docs.dify.ai/en/develop-plugin/features-and-specs/plugin-types/"
    "multilingual-readme#multilingual-readme"
)


def check_project_structure(plugin_dir: Path) -> List[CheckResult]:
    """Quick structural review of the unpacked plugin before heavy checks."""
    results: List[CheckResult] = []
    missing: List[str] = []
    present: List[str] = []

    for name in REQUIRED_FILES:
        if (plugin_dir / name).exists():
            present.append(name)
        else:
            missing.append(name)

    for name in EXPECTED_FILES:
        if (plugin_dir / name).exists():
            present.append(name)
        else:
            missing.append(name)

    assets_dir = plugin_dir / "_assets"
    has_assets = assets_dir.is_dir() and any(assets_dir.iterdir())

    if missing:
        results.append(CheckResult(
            "Project structure",
            False,
            f"Missing files: {', '.join(missing)}. Present: {', '.join(present)}. _assets/: {'yes' if has_assets else 'no'}.",
        ))
    else:
        results.append(CheckResult(
            "Project structure",
            True,
            f"All expected files present: {', '.join(present)}. _assets/: {'yes' if has_assets else 'no'}.",
        ))

    return results


def check_privacy_md(plugin_dir: Path) -> CheckResult:
    """Verify PRIVACY.md exists in the plugin package."""
    privacy_path = plugin_dir / "PRIVACY.md"
    if not privacy_path.exists():
        return CheckResult(
            "PRIVACY.md",
            False,
            "PRIVACY.md not found in plugin package. "
            "A privacy policy file is required for marketplace submission.",
        )
    content = privacy_path.read_text(encoding="utf-8", errors="ignore").strip()
    if not content:
        return CheckResult(
            "PRIVACY.md",
            False,
            "PRIVACY.md is empty. Please provide a privacy policy.",
        )
    return CheckResult("PRIVACY.md", True, "PRIVACY.md exists and is non-empty.")


def readme_language_result(
    plugin_dir: Path,
    max_cjk: int,
) -> CheckResult:
    readme_path = plugin_dir / "README.md"
    if not readme_path.exists():
        return CheckResult("README language", False, "README.md not found in plugin package.")

    text = strip_code_blocks(readme_path.read_text(encoding="utf-8", errors="ignore"))
    zh_count = len(re.findall(r"[\u3400-\u4DBF\u4E00-\u9FFF]", text))
    en_count = len(re.findall(r"[A-Za-z]", text))
    total = zh_count + en_count
    ratio = (zh_count / total) if total else 0.0

    detail = f"README.md CJK ratio={ratio:.1%} (zh={zh_count}, en={en_count}, allowed_zh<={max_cjk})"

    if zh_count > max_cjk:
        return CheckResult(
            "README language",
            False,
            detail
            + "; Chinese characters are not allowed. "
            + f"Use multilingual README guidance: {README_MULTILINGUAL_DOC_URL}",
        )

    return CheckResult("README language", True, detail)


def markdown_table_cell(text: str, limit: int = 260) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if len(normalized) > limit:
        normalized = normalized[: limit - 1].rstrip() + "…"
    return normalized.replace("|", "\\|")


def markdown_results_table(results: List[CheckResult]) -> List[str]:
    lines = [
        "| Check | Status | Detail |",
        "|---|---|---|",
    ]
    for result in results:
        status = "✅ Pass" if result.ok else "❌ Fail"
        detail = markdown_table_cell(result.detail)
        lines.append(f"| `{result.name}` | {status} | {detail} |")
    return lines


def collect_failures(results: List[CheckResult]) -> List[CheckResult]:
    return [r for r in results if not r.ok]


def build_review_body(results: List[CheckResult], approve_message: str) -> Tuple[bool, str]:
    failures = collect_failures(results)
    if not failures:
        lines = [
            f"## ✅ {approve_message}",
            "",
            "> **Decision:** Approve",
            "",
            "### Local Check Results",
            *markdown_results_table(results),
        ]
        return True, "\n".join(lines)

    lines = [
        "## ❌ Request Changes",
        "",
        "> **Decision:** Request changes",
        "",
        "### Failed Checks",
        *markdown_results_table(failures),
        "",
        "### Full Check Results",
        *markdown_results_table(results),
        "",
        "### Required Fixes",
    ]
    for result in failures:
        lines.append(f"- **{result.name}**: {result.detail}")
    lines.extend(
        [
            "",
            "Please address these issues and push an update.",
        ]
    )
    return False, "\n".join(lines)


def post_review(pr_ref: str, repo: str, approved: bool, body: str) -> None:
    event = "--approve" if approved else "--request-changes"
    run_cmd(["gh", "pr", "review", pr_ref, "-R", repo, event, "-b", body])


def prepare_plugin_dir(pkg_path: Path, temp_root: Path) -> Path:
    if not pkg_path.exists():
        raise CheckFailed(f"Plugin package file not found: {pkg_path}")

    zip_path = temp_root / (pkg_path.name + ".zip")
    shutil.copy2(pkg_path, zip_path)

    unpacked = temp_root / "unpacked_plugin"
    unpacked.mkdir(parents=True, exist_ok=True)
    unzip_result = run_cmd(["unzip", "-q", str(zip_path), "-d", str(unpacked)], check=False)
    if unzip_result.returncode != 0:
        print("unzip failed; retrying extraction with Python zipfile.", file=sys.stderr)
        shutil.rmtree(unpacked, ignore_errors=True)
        unpacked.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(zip_path) as archive:
                for member in archive.infolist():
                    member_path = Path(member.filename)
                    if member_path.is_absolute() or ".." in member_path.parts:
                        raise CheckFailed(f"Unsafe path in package: {member.filename}")
                archive.extractall(unpacked)
        except CheckFailed:
            raise
        except Exception as exc:
            raise CheckFailed(f"Failed to unpack plugin package with Python zipfile: {exc}") from exc
    return unpacked


def clone_toolkit(temp_root: Path) -> Path:
    toolkit_dir = temp_root / "toolkit"
    run_cmd(["gh", "repo", "clone", "langgenius/dify-marketplace-toolkit", str(toolkit_dir)])
    return toolkit_dir


def download_daemon(temp_root: Path) -> Path:
    pattern = daemon_pattern_for_host()
    run_cmd(
        [
            "gh",
            "release",
            "download",
            "-R",
            "langgenius/dify-plugin-daemon",
            "--pattern",
            pattern,
            "--dir",
            str(temp_root),
        ]
    )
    daemon = temp_root / pattern
    daemon.chmod(0o755)
    return daemon


def resolve_pkg_file(pr_data: dict) -> str:
    files = [item.get("path", "") for item in pr_data.get("files", [])]
    pkg_files = [path for path in files if path.endswith(".difypkg")]
    if len(pkg_files) != 1:
        raise CheckFailed(
            "Exactly one .difypkg file must be changed in PR. "
            f"Found {len(pkg_files)}: {pkg_files}"
        )
    return pkg_files[0]


def print_report(results: List[CheckResult]) -> None:
    total = len(results)
    failures = collect_failures(results)
    passed = total - len(failures)

    lines = [
        "",
        "## Local Review Results",
        "",
        f"- **Total checks:** {total}",
        f"- **Passed:** {passed}",
        f"- **Failed:** {len(failures)}",
        "",
        "### Check Table",
        *markdown_results_table(results),
    ]
    if failures:
        lines.extend(
            [
                "",
                "### Failed Check Highlights",
                *[f"- **{item.name}**: {item.detail}" for item in failures],
            ]
        )

    print("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run local checks for a Dify plugin PR and optionally submit GH review.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """
            Example:
              python3 scripts/review_pr.py --pr https://github.com/langgenius/dify-plugins/pull/1939 --submit-review
            """
        ).strip(),
    )
    parser.add_argument("--pr", required=True, help="PR number or PR URL")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="owner/repo (default: langgenius/dify-plugins)")
    parser.add_argument("--workdir", default=".", help="Local repository path")
    parser.add_argument(
        "--python-cmd",
        default=None,
        help="Python interpreter command for venv/checks (auto-detect >=3.11 when omitted)",
    )
    parser.add_argument(
        "--marketplace-base-url",
        default=DEFAULT_MARKETPLACE_BASE_URL,
        help="Marketplace base URL",
    )
    parser.add_argument(
        "--marketplace-token",
        default=DEFAULT_MARKETPLACE_TOKEN,
        help="Marketplace token for upload-package.py",
    )
    parser.add_argument(
        "--readme-max-cjk",
        type=int,
        default=DEFAULT_README_MAX_CJK,
        help="Maximum allowed CJK characters in README.md (default: 0)",
    )
    parser.add_argument(
        "--pr-content-max-cjk",
        type=int,
        default=DEFAULT_PR_CONTENT_MAX_CJK,
        help="Maximum allowed CJK characters in PR title/body after allowlist filtering (default: 0)",
    )
    parser.add_argument(
        "--allow-pr-cjk-snippet",
        action="append",
        default=[],
        help=(
            "Allowlisted PR title/body snippet that may contain CJK. "
            "Repeatable. Default includes the bilingual notice sentence used in templates."
        ),
    )
    parser.add_argument(
        "--approve-message",
        default="LGTM",
        help="Approval message when checks pass",
    )
    parser.add_argument(
        "--submit-review",
        action="store_true",
        help="Submit gh review automatically",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep temp workspace for debugging",
    )
    args = parser.parse_args()

    try:
        for cmd in ("gh", "jq", "unzip", "git"):
            ensure_command_exists(cmd)

        python_cmd = detect_python_cmd(args.python_cmd)

        workdir = Path(args.workdir).resolve()
        if not (workdir / ".git").exists():
            raise CheckFailed(f"workdir is not a git repository: {workdir}")

        original_branch = current_branch(workdir)
        pr_branch = ""

        pr_data = gh_json(args.pr, args.repo, "number,url,title,body,files")
        checkout_pr(args.pr, args.repo, workdir)
        pr_branch = current_branch(workdir)

        pkg_relpath = resolve_pkg_file(pr_data)
        pkg_path = workdir / pkg_relpath

        temp_root_obj = tempfile.TemporaryDirectory(prefix="pr-review-helper-")
        temp_root = Path(temp_root_obj.name)

        results: List[CheckResult] = []
        approved = False
        body = ""

        try:
            allowed_pr_snippets = list(DEFAULT_ALLOWED_PR_CJK_SNIPPETS)
            if args.allow_pr_cjk_snippet:
                allowed_pr_snippets.extend(args.allow_pr_cjk_snippet)

            results.append(
                pr_content_language_result(
                    pr_data,
                    args.pr_content_max_cjk,
                    allowed_pr_snippets,
                )
            )

            plugin_dir = prepare_plugin_dir(pkg_path, temp_root)

            # Quick structural review before heavy checks
            results.extend(check_project_structure(plugin_dir))

            try:
                manifest = parse_manifest(plugin_dir / "manifest.yaml")
                results.append(check_manifest_author(manifest))
                results.append(check_icon(plugin_dir, manifest))
                results.append(check_version_availability(args.marketplace_base_url, manifest))
            except CheckFailed as exc:
                results.append(failure_result("Manifest parsing", str(exc)))
                manifest = {}

            results.append(
                readme_language_result(
                    plugin_dir,
                    args.readme_max_cjk,
                )
            )
            results.append(check_privacy_md(plugin_dir))

            toolkit_dir: Path | None = None
            daemon_path: Path | None = None
            python_bin: Path | None = None
            pip_bin: Path | None = None

            try:
                toolkit_dir = clone_toolkit(temp_root)
                daemon_path = download_daemon(temp_root)
                venv_dir = temp_root / ".venv"
                python_bin, pip_bin = build_toolkit_env(venv_dir, python_cmd)
            except CheckFailed as exc:
                results.append(failure_result("Environment setup", str(exc)))

            if python_bin and pip_bin and toolkit_dir and daemon_path:
                try:
                    results.append(install_plugin_deps(pip_bin, plugin_dir))
                except CheckFailed as exc:
                    results.append(failure_result("Dependency install", str(exc)))

                results.append(check_dify_plugin_version(pip_bin, MIN_DIFY_PLUGIN_VERSION))

                try:
                    results.append(run_install_test(python_bin, pip_bin, toolkit_dir, plugin_dir))
                except CheckFailed as exc:
                    results.append(failure_result("Install test", str(exc)))

                try:
                    results.append(
                        run_packaging_test(
                            python_bin,
                            toolkit_dir,
                            daemon_path,
                            plugin_dir,
                            args.marketplace_base_url,
                            args.marketplace_token,
                        )
                    )
                except CheckFailed as exc:
                    results.append(failure_result("Packaging test", str(exc)))
            else:
                results.append(
                    failure_result(
                        "Dependency install",
                        "Skipped because environment setup failed.",
                    )
                )
                results.append(
                    failure_result(
                        "dify_plugin version",
                        "Skipped because environment setup failed.",
                    )
                )
                results.append(
                    failure_result(
                        "Install test",
                        "Skipped because environment setup failed.",
                    )
                )
                results.append(
                    failure_result(
                        "Packaging test",
                        "Skipped because environment setup failed.",
                    )
                )

            print_report(results)
            approved, body = build_review_body(results, args.approve_message)
            print("\n## Suggested Review Body")
            print(body)

            if args.submit_review:
                post_review(args.pr, args.repo, approved, body)
                print("\nSubmitted review via gh.")
        finally:
            if args.keep_temp:
                print(f"Temp artifacts kept at: {temp_root}")
            else:
                temp_root_obj.cleanup()

            if original_branch and original_branch != "HEAD":
                run_cmd(["git", "checkout", original_branch], cwd=workdir, check=False)
            if pr_branch and pr_branch not in {"HEAD", original_branch}:
                delete_local_branch(workdir, pr_branch)

        return 0 if approved else 1

    except CheckFailed as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired as exc:
        print(f"ERROR: Command timed out: {' '.join(exc.cmd)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
