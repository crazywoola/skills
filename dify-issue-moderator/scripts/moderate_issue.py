#!/usr/bin/env python3
"""Moderate Dify issues using GitHub CLI."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from typing import Iterable, Sequence

PLUGIN_REPOS = {"langgenius/dify-plugins", "langgenius/dify-official-plugins"}
CORE_REPO = "langgenius/dify"
WEBAPP_REPOS = {"langgenius/webapp-conversation", "langgenius/webapp-text-generator"}
CORE_LIKE_REPOS = {CORE_REPO} | WEBAPP_REPOS
SUPPORTED_REPOS = PLUGIN_REPOS | CORE_LIKE_REPOS
SKIP_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR", "CONTRIBUTOR"}
CJK_RATIO_THRESHOLD = 0.20
MIN_DIFY_VERSION = (1, 10, 0)
MIN_DIFY_VERSION_STR = "1.10.0"

FORUM_URL = "https://forum.dify.ai/"
DISCORD_URL = "https://discord.com/invite/FngNHpbcY7"
BUG_TEMPLATE_URL = (
    "https://github.com/langgenius/dify/blob/"
    "3aecceff27c6b712628ad463c6e6ac15b8527ebe/.github/ISSUE_TEMPLATE/bug_report.yml"
)
CODE_OF_CONDUCT_URL = (
    "https://github.com/langgenius/dify/blob/"
    "4c1ad40f8e8a6ee58a958330558f2178b7e47fa7/.github/CODE_OF_CONDUCT.md"
)
CONTRIBUTING_URL = (
    "https://github.com/langgenius/dify/blob/"
    "25ac69afc5ac9324079be5f0d02b2a2b03dcc784/CONTRIBUTING.md"
)

ISSUE_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<number>\d+)(?:[/?#].*)?$"
)
CJK_RE = re.compile(
    r"["
    r"\u2e80-\u2eff"  # CJK Radicals Supplement
    r"\u3000-\u303f"  # CJK Symbols and Punctuation
    r"\u3040-\u309f"  # Hiragana
    r"\u30a0-\u30ff"  # Katakana
    r"\u3100-\u312f"  # Bopomofo
    r"\u3130-\u318f"  # Hangul Compatibility Jamo
    r"\u3200-\u32ff"  # Enclosed CJK Letters and Months
    r"\u3300-\u33ff"  # CJK Compatibility
    r"\u3400-\u4dbf"  # CJK Unified Ideographs Extension A
    r"\u4e00-\u9fff"  # CJK Unified Ideographs
    r"\uac00-\ud7af"  # Hangul Syllables
    r"\uf900-\ufaff"  # CJK Compatibility Ideographs
    r"\ufe30-\ufe4f"  # CJK Compatibility Forms
    r"\uff01-\uff60"  # Fullwidth Forms (，。？！etc.)
    r"\uffe0-\uffef"  # Fullwidth Signs
    r"]"
)
SELF_CHECKS_HEADER_RE = re.compile(r"^#{1,6}\s*Self Checks\s*$", re.IGNORECASE)
ALLOWED_SELF_CHECKS_CJK_SNIPPETS = (
    "我已阅读并同意",
    "请务必使用英文提交 Issue，否则会被关闭。谢谢！:)",
)
DIFY_VERSION_LINE_RE = re.compile(r"\bdify\s*version\b", re.IGNORECASE)
DIFY_VERSION_INLINE_RE = re.compile(r"\bdify\s*v?(\d+)\.(\d+)(?:\.(\d+))?\b", re.IGNORECASE)
SEMVER_RE = re.compile(r"\bv?(\d+)\.(\d+)(?:\.(\d+))?\b")
QUESTION_START_RE = re.compile(
    r"^\s*(how|what|why|can|could|is|are|do|does|did|where|when|which|who|whom|help)\b",
    re.IGNORECASE,
)
FEATURE_STORY_SECTION_RE = re.compile(
    r"(?is)#+\s*1\.\s*Is this request related to a challenge you're experiencing\?.*?\n\n(.*?)(?=\n#+\s*2\.|\Z)"
)
PLACEHOLDER_RE = re.compile(r"\b(tbd|todo|n/?a|none|same as title|no idea)\b", re.IGNORECASE)
GENERIC_TITLE_RE = re.compile(
    r"^(bug|issue|help|question|error|problem|bug report|help me|fix this|"
    r"not working|doesn'?t work|please help|request|suggestion)$",
    re.IGNORECASE,
)
DISRESPECTFUL_RE = re.compile(r"\b(idiot|stupid|dumb|fuck|shit|bitch)\b", re.IGNORECASE)
NON_RESPONSE_VALUES = {"_no response_", "n/a", "na", "none"}
BUG_MARKERS_RE = re.compile(
    r"\b(bug|error|exception|traceback|crash|fail(?:s|ure)?)\b",
    re.IGNORECASE,
)


@dataclass
class IssueData:
    repo: str
    number: int
    title: str
    body: str
    author: str
    labels: list[str]
    state: str
    url: str
    author_association: str
    linked_prs: list[str]


@dataclass
class Decision:
    action: str
    category: str
    reasons: list[str]
    comment: str = ""


def run_cmd(cmd: Sequence[str], *, check: bool = True) -> str:
    result = subprocess.run(
        list(cmd),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(cmd)}\n{message}")
    return result.stdout


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def parse_issue_target(issue_ref: str, repo_override: str | None) -> tuple[str, int]:
    match = ISSUE_URL_RE.match(issue_ref.strip())
    if match:
        repo = f"{match.group('owner')}/{match.group('repo')}"
        if repo_override and repo_override != repo:
            raise ValueError(f"--repo {repo_override} does not match issue URL repo {repo}")
        return repo, int(match.group("number"))

    if not issue_ref.isdigit():
        raise ValueError("--issue must be a GitHub issue URL or an issue number")
    if not repo_override:
        raise ValueError("--repo is required when --issue is a number")
    return repo_override, int(issue_ref)


def fetch_issue(repo: str, issue_number: int) -> IssueData:
    issue_raw = run_cmd(
        [
            "gh",
            "issue",
            "view",
            str(issue_number),
            "-R",
            repo,
            "--json",
            "number,title,body,author,labels,state,url,closedByPullRequestsReferences",
        ]
    )
    payload = json.loads(issue_raw)

    association = run_cmd(
        ["gh", "api", f"repos/{repo}/issues/{issue_number}", "--jq", ".author_association"]
    ).strip()

    labels = [
        item.get("name", "").strip()
        for item in payload.get("labels", [])
        if item.get("name", "").strip()
    ]
    linked_prs_raw = payload.get("closedByPullRequestsReferences") or []
    linked_prs = [
        pr.get("url")
        for pr in linked_prs_raw
        if isinstance(pr, dict) and pr.get("url")
    ]

    author_info = payload.get("author") or {}
    return IssueData(
        repo=repo,
        number=int(payload.get("number", issue_number)),
        title=payload.get("title") or "",
        body=payload.get("body") or "",
        author=author_info.get("login") or "unknown",
        labels=labels,
        state=payload.get("state") or "UNKNOWN",
        url=payload.get("url") or "",
        author_association=association or "NONE",
        linked_prs=linked_prs,
    )


def cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    total = sum(1 for ch in text if not ch.isspace())
    if total == 0:
        return 0.0
    cjk_count = sum(1 for ch in text if CJK_RE.match(ch))
    return cjk_count / total


def sanitize_body_for_cjk(body: str) -> str:
    lines = body.splitlines()
    sanitized: list[str] = []
    in_self_checks = False

    for line in lines:
        heading_match = re.match(r"^#{1,6}\s+.*", line.strip())
        if heading_match:
            in_self_checks = bool(SELF_CHECKS_HEADER_RE.match(line.strip()))
            sanitized.append(line)
            continue

        if in_self_checks and any(snippet in line for snippet in ALLOWED_SELF_CHECKS_CJK_SNIPPETS):
            cleaned = line
            for snippet in ALLOWED_SELF_CHECKS_CJK_SNIPPETS:
                cleaned = cleaned.replace(snippet, "")
            if cleaned.strip() in {"- [x]", "- [ ]", "- [X]", "* [x]", "* [ ]", "* [X]", ""}:
                continue
            sanitized.append(cleaned)
            continue

        sanitized.append(line)

    return "\n".join(sanitized)


def parse_semver(text: str) -> tuple[int, int, int] | None:
    match = SEMVER_RE.search(text)
    if not match:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def extract_dify_version(body: str) -> tuple[int, int, int] | None:
    if not body:
        return None
    for line in body.splitlines():
        if DIFY_VERSION_LINE_RE.search(line):
            version = parse_semver(line)
            if version:
                return version
    match = DIFY_VERSION_INLINE_RE.search(body)
    if match:
        return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)
    return None


def language_check_text(issue: IssueData) -> str:
    sanitized_body = sanitize_body_for_cjk(issue.body)
    return f"{issue.title}\n{sanitized_body}"


def looks_like_question(issue: IssueData) -> bool:
    labels_lower = {label.lower() for label in issue.labels}
    if "question" in labels_lower or "support" in labels_lower:
        return True

    title = issue.title.strip()
    if "?" in title or "？" in title:
        return True
    if QUESTION_START_RE.match(title):
        return True

    body_head = normalize_space("\n".join(issue.body.splitlines()[:10])).lower()
    markers = (
        "how to ",
        "what is ",
        "can i ",
        "could i ",
        "any idea",
        "anyone know",
        "need help",
        "i want to know",
        "please tell me",
        "i'm wondering",
        "i am wondering",
        "is there a way",
        "is it possible",
        "does anyone",
        "has anyone",
        "please help",
        "how can i",
        "how do i",
        "where can i",
    )
    return any(marker in body_head for marker in markers)


SKIP_SECTION_HEADINGS = {"self checks", "self check"}


def extract_template_sections(body: str) -> list[tuple[str, str]]:
    """Extract (heading, content) pairs from markdown template sections."""
    sections: list[tuple[str, str]] = []
    current_heading = ""
    current_lines: list[str] = []

    for line in body.splitlines():
        stripped = line.strip()
        heading_match = re.match(r"^#{1,6}\s+(.*)", stripped)
        if heading_match:
            if current_heading:
                sections.append((current_heading, "\n".join(current_lines).strip()))
            current_heading = heading_match.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_heading:
        sections.append((current_heading, "\n".join(current_lines).strip()))

    return sections


def effective_content(body: str) -> str:
    """Return meaningful content, stripping template headings, checkboxes, and _No response_ values."""
    sections = extract_template_sections(body)
    if not sections:
        return normalize_space(body)

    parts: list[str] = []
    for heading, content in sections:
        if heading.lower() in SKIP_SECTION_HEADINGS:
            continue
        content_clean = normalize_space(content)
        if not content_clean or content_clean.lower() in NON_RESPONSE_VALUES:
            continue
        # Skip if content is only checkboxes
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        if lines and all(re.match(r"^[-*]\s*\[[ xX]\]", ln) for ln in lines):
            continue
        parts.append(content_clean)

    return " ".join(parts) if parts else normalize_space(body)


def unclear_reasons(issue: IssueData) -> list[str]:
    reasons: list[str] = []
    title_clean = normalize_space(issue.title)
    body_clean = normalize_space(issue.body)
    body_lower = body_clean.lower()
    # Use effective content (strips template boilerplate and _No response_ values)
    content = effective_content(issue.body)
    content_len = len(content)

    if len(title_clean) < 8 or GENERIC_TITLE_RE.fullmatch(title_clean):
        reasons.append("Title is too short or generic.")

    if not body_clean:
        reasons.append("Description is empty.")
        return reasons

    if content_len < 60:
        reasons.append("Description is too short to understand the task.")

    if PLACEHOLDER_RE.search(body_clean):
        reasons.append("Description contains placeholders instead of concrete details.")

    # Check for template sections that are all _No response_ or empty
    sections = extract_template_sections(issue.body)
    if sections:
        filled = sum(
            1 for _, c in sections
            if normalize_space(c).lower() not in NON_RESPONSE_VALUES
            and normalize_space(c)
            and c.lower() not in SKIP_SECTION_HEADINGS
        )
        if filled <= 1:
            reasons.append("Almost all template sections are empty or marked _No response_.")

    detail_markers = (
        "steps",
        "reproduce",
        "expected",
        "actual",
        "error",
        "log",
        "screenshot",
        "use case",
        "environment",
        "version",
    )
    marker_hits = sum(1 for marker in detail_markers if marker in body_lower)
    if content_len < 180 and marker_hits < 2:
        reasons.append("Description lacks enough concrete context for maintainers.")

    return dedupe(reasons)


def is_bug_like(issue: IssueData) -> bool:
    labels_lower = {label.lower() for label in issue.labels}
    if "bug" in labels_lower:
        return True
    combined = f"{issue.title}\n{issue.body}".lower()
    return bool(BUG_MARKERS_RE.search(combined))


def is_feature_like(issue: IssueData) -> bool:
    labels_lower = {label.lower() for label in issue.labels}
    if "feature" in labels_lower or "enhancement" in labels_lower:
        return True
    combined = f"{issue.title}\n{issue.body}".lower()
    markers = ("feature request", "feature", "enhancement", "proposal", "suggestion")
    return any(marker in combined for marker in markers)


def extract_feature_story(body: str) -> str:
    match = FEATURE_STORY_SECTION_RE.search(body or "")
    if not match:
        return ""
    return match.group(1).strip()


def feature_request_quality(issue: IssueData) -> bool:
    body = issue.body or ""
    body_lower = body.lower()
    body_clean = normalize_space(body)
    if not body_clean:
        return False

    story = normalize_space(extract_feature_story(body))
    if story and story.lower() not in NON_RESPONSE_VALUES and len(story) >= 60:
        return True

    if "example" in body_lower and ("expected output" in body_lower or "expected" in body_lower):
        return True

    if re.search(r"\b(add|support|allow|enable|expose|visualize|customize)\b", body_lower):
        return len(body_clean) >= 120

    return False


def core_standard_violations(issue: IssueData) -> list[str]:
    violations: list[str] = []
    title_clean = normalize_space(issue.title)
    body_clean = normalize_space(issue.body)
    body_lower = issue.body.lower()

    if len(title_clean) < 12 or GENERIC_TITLE_RE.fullmatch(title_clean):
        violations.append("Use a clear and descriptive issue title.")

    if len(body_clean) < 120:
        violations.append("Provide a detailed issue description with enough context.")

    if DISRESPECTFUL_RE.search(f"{issue.title}\n{issue.body}"):
        violations.append("Use respectful, professional language (Code of Conduct).")

    if is_bug_like(issue):
        required = {
            "Dify version": (r"\bdify version\b", r"\bversion\b"),
            "deployment mode (Cloud or Self Hosted)": (
                r"\bcloud\b",
                r"self[- ]hosted",
                r"\bdocker\b",
                r"\bsource\b",
            ),
            "steps to reproduce": (r"steps to reproduce", r"\breproduce\b", r"^\s*1[.)]\s+"),
            "expected behavior": (r"expected behavior", r"\bexpected\b"),
        }
        for label, patterns in required.items():
            if not any(re.search(pattern, body_lower, re.MULTILINE) for pattern in patterns):
                violations.append(f"Include {label}.")
        if not any(
            re.search(pattern, body_lower, re.MULTILINE)
            for pattern in (r"actual behavior", r"\bactual\b", r"\blog", r"\berror\b", r"traceback")
        ):
            violations.append("Include actual behavior and logs/error details when possible.")

    if is_feature_like(issue):
        feature_markers = ("use case", "scenario", "business value", "why this is needed", "motivation")
        if not any(marker in body_lower for marker in feature_markers) and not feature_request_quality(issue):
            violations.append("Describe the feature use case and expected value.")

    return dedupe(violations)


def render_comment(issue: IssueData, category: str, reasons: list[str]) -> str:
    reason_lines = "\n".join(f"- {item}" for item in reasons)
    author = issue.author

    if category == "question":
        return textwrap.dedent(
            f"""\
            Hi @{author}, thanks for opening this issue.

            ### Why this is being closed
            This issue tracker is reserved for actionable bugs/tasks. This report looks like a usage question.

            ### Next steps
            Please use the community channels instead:
            - {FORUM_URL}
            - {DISCORD_URL}

            If this is actually a bug/task, please open a new issue with clear reproducible details.

            Thanks for understanding and for supporting Dify.
            """
        ).strip()

    if category == "language":
        return textwrap.dedent(
            f"""\
            Hi @{author}, thanks for opening this issue.

            ### Why this is being closed
            Dify issue tracking requires English-only issue title and description for consistent collaboration.

            ### Next steps
            Please open a new issue in English and include clear details so maintainers can help efficiently.

            Thanks for understanding and for your support.
            """
        ).strip()

    if category == "unclear":
        reasons_block = reason_lines or "- The issue content is not clear enough to triage."
        return "\n".join([
            f"Hi @{author}, thanks for opening this issue.",
            "",
            "### Why this is being closed",
            "We could not extract an actionable task from the current report.",
            "",
            reasons_block,
            "",
            "### Next steps",
            "Please open a new issue that includes:",
            "- A clear problem statement",
            "- Reproducible steps or concrete scope",
            "- Expected result",
            "- Actual result and logs/screenshots when available",
            "",
            "Thanks for understanding and for helping keep the issue tracker actionable.",
        ])

    if category == "outdated-version":
        reasons_block = reason_lines or f"- Reported Dify version is below v{MIN_DIFY_VERSION_STR}."
        return "\n".join([
            f"Hi @{author}, thanks for opening this issue.",
            "",
            "### Why this is being closed",
            "This report targets an outdated Dify version.",
            "",
            reasons_block,
            "",
            "### Next steps",
            "Please upgrade to the latest Dify release and retest. If the issue still occurs on the latest version, open a new issue with updated details.",
            "",
            "Thanks for understanding and for supporting Dify.",
        ])

    if category == "core-standards":
        reasons_block = reason_lines or "- Required issue details are missing."
        return "\n".join([
            f"Hi @{author}, thanks for opening this issue.",
            "",
            "### Why this is being closed",
            f"This report does not yet meet the required issue standard for `{issue.repo}`.",
            "",
            reasons_block,
            "",
            "### Relevant guidelines",
            f"- Bug report template: {BUG_TEMPLATE_URL}",
            f"- Code of Conduct / Language Policy: {CODE_OF_CONDUCT_URL}",
            f"- Contributing guide: {CONTRIBUTING_URL}",
            "",
            "### Next steps",
            "Please open a new issue in English and include all required details from the bug template/contributing guide.",
            "",
            "Thanks for understanding and for your contribution.",
        ])

    return ""


def decide(issue: IssueData) -> Decision:
    if issue.repo not in SUPPORTED_REPOS:
        return Decision(
            action="skip",
            category="unsupported-repo",
            reasons=[f"Repository '{issue.repo}' is not supported by this skill."],
        )

    if issue.state.upper() != "OPEN":
        return Decision(
            action="skip",
            category="not-open",
            reasons=[f"Issue state is {issue.state}. No moderation action required."],
        )

    language_text = language_check_text(issue)
    combined_ratio = cjk_ratio(language_text)
    # Also check body alone to catch cases where a long English title dilutes the ratio
    body_ratio = cjk_ratio(sanitize_body_for_cjk(issue.body))
    ratio = max(combined_ratio, body_ratio)
    has_cjk = ratio >= CJK_RATIO_THRESHOLD
    is_question = looks_like_question(issue)

    if issue.repo in PLUGIN_REPOS:
        if has_cjk:
            reasons = [f"CJK ratio is {ratio:.1%} (>= {CJK_RATIO_THRESHOLD:.0%})."]
            return Decision(
                action="close",
                category="language",
                reasons=reasons,
                comment=render_comment(issue, "language", reasons),
            )
        if is_question:
            reasons = ["Issue appears to be a question rather than an actionable task."]
            return Decision(
                action="close",
                category="question",
                reasons=reasons,
                comment=render_comment(issue, "question", reasons),
            )
        reasons = unclear_reasons(issue)
        if reasons:
            return Decision(
                action="close",
                category="unclear",
                reasons=reasons,
                comment=render_comment(issue, "unclear", reasons),
            )
        return Decision(
            action="none",
            category="pass",
            reasons=["Issue appears actionable and follows repository moderation rules."],
        )

    if issue.repo in CORE_LIKE_REPOS and issue.linked_prs:
        reasons = [f"Issue has {len(issue.linked_prs)} linked PR(s); skip review per policy."]
        return Decision(
            action="skip",
            category="linked-pr",
            reasons=reasons,
        )

    association = issue.author_association.upper()
    if issue.repo in CORE_LIKE_REPOS and association in SKIP_ASSOCIATIONS:
        return Decision(
            action="skip",
            category="trusted-author",
            reasons=[f"Author association is {association}; skip review per policy."],
        )

    if has_cjk:
        reasons = [f"CJK ratio is {ratio:.1%} (>= {CJK_RATIO_THRESHOLD:.0%})."]
        return Decision(
            action="close",
            category="language",
            reasons=reasons,
            comment=render_comment(issue, "language", reasons),
        )

    if is_question:
        reasons = ["Issue appears to be a question rather than an actionable bug/task."]
        return Decision(
            action="close",
            category="question",
            reasons=reasons,
            comment=render_comment(issue, "question", reasons),
        )

    if issue.repo == CORE_REPO:
        reported_version = extract_dify_version(issue.body)
        if reported_version and reported_version < MIN_DIFY_VERSION:
            version_str = ".".join(str(part) for part in reported_version)
            reasons = [
                f"Reported Dify version is v{version_str}, which is below v{MIN_DIFY_VERSION_STR}."
            ]
            return Decision(
                action="close",
                category="outdated-version",
                reasons=reasons,
                comment=render_comment(issue, "outdated-version", reasons),
            )

    violations = core_standard_violations(issue)
    if violations:
        return Decision(
            action="close",
            category="core-standards",
            reasons=violations,
            comment=render_comment(issue, "core-standards", violations),
        )

    return Decision(
        action="none",
        category="pass",
        reasons=["Issue meets baseline moderation and quality standards."],
    )


def print_summary(issue: IssueData, decision: Decision) -> None:
    print(f"Repository: {issue.repo}")
    print(f"Issue: #{issue.number} - {issue.title}")
    print(f"URL: {issue.url}")
    print(f"Author: @{issue.author} ({issue.author_association})")
    print(f"Decision: {decision.action.upper()} [{decision.category}]")
    if decision.reasons:
        print("Reasons:")
        for reason in decision.reasons:
            print(f"- {reason}")
    if decision.comment:
        print("\nComment preview:\n")
        print(decision.comment)


def close_issue(issue: IssueData, comment: str) -> None:
    run_cmd(
        [
            "gh",
            "issue",
            "close",
            str(issue.number),
            "-R",
            issue.repo,
            "--reason",
            "not planned",
            "--comment",
            comment,
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Moderate Dify issues with gh.")
    parser.add_argument("--issue", required=True, help="Issue URL or issue number.")
    parser.add_argument("--repo", help="owner/repo (required when --issue is a number).")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply close action in GitHub. Default mode is dry-run.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print decision payload as JSON in addition to human-readable output.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        repo, issue_number = parse_issue_target(args.issue, args.repo)
        issue = fetch_issue(repo, issue_number)
        decision = decide(issue)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print_summary(issue, decision)

    if args.json:
        print(
            json.dumps(
                {
                    "repo": issue.repo,
                    "issue_number": issue.number,
                    "decision": decision.action,
                    "category": decision.category,
                    "reasons": decision.reasons,
                },
                indent=2,
            )
        )

    if decision.action == "close":
        if args.apply:
            try:
                close_issue(issue, decision.comment)
            except Exception as exc:  # noqa: BLE001
                print(f"[ERROR] Failed to close issue: {exc}", file=sys.stderr)
                return 1
            print("\nApplied moderation: issue closed with comment.")
        else:
            print("\nDry run only. Re-run with --apply to close the issue.")
    else:
        print("\nNo close action applied.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
