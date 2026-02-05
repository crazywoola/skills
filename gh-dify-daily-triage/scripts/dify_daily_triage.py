#!/usr/bin/env python3
"""
Generate a daily triage report for Dify GitHub repos using gh.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from typing import Iterable

DEFAULT_REPOS = [
    "langgenius/dify",
    "langgenius/dify-plugins",
    "langgenius/dify-official-plugins",
    "langgenius/webapp-conversation",
    "langgenius/webapp-text-generator",
    "langgenius/dify-docs",
    "langgenius/dify-plugin-daemon",
]


def _clean_env(no_proxy: bool) -> dict[str, str]:
    if not no_proxy:
        return os.environ.copy()
    env = os.environ.copy()
    for key in (
        "all_proxy",
        "http_proxy",
        "https_proxy",
        "ALL_PROXY",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "no_proxy",
        "NO_PROXY",
    ):
        env.pop(key, None)
    return env


def _gh_json(args: list[str], env: dict[str, str]) -> list[dict]:
    try:
        output = subprocess.check_output(["gh"] + args, text=True, env=env)
    except subprocess.CalledProcessError as exc:
        sys.stderr.write("gh command failed. Check gh auth status and proxy settings.\n")
        sys.stderr.write(f"Command: gh {' '.join(args)}\n")
        sys.stderr.write(exc.output or "")
        raise
    return json.loads(output) if output.strip() else []


def _escape_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _join_labels(labels: Iterable[dict]) -> str:
    names = [label.get("name", "").strip() for label in labels or [] if label.get("name")]
    return ", ".join(names) if names else "-"


def _linked_items(items: Iterable[dict], prefix: str) -> str:
    links = []
    for item in items or []:
        number = item.get("number")
        url = item.get("url")
        if number and url:
            links.append(f"[#{number}]({url})")
    if links:
        return f"{prefix}: " + ", ".join(links)
    return f"no-{prefix}"


def _print_table(title: str, columns: list[str], rows: list[list[str]]) -> None:
    print(f"### {title}")
    if not rows:
        empty_label = "PRs" if title.lower() == "prs" else title.lower()
        print(f"No {empty_label} created today.")
        return
    print("| " + " | ".join(columns) + " |")
    print("| " + " | ".join(["---"] * len(columns)) + " |")
    for row in rows:
        print("| " + " | ".join(row) + " |")


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily triage report for Dify repos.")
    parser.add_argument(
        "--date",
        default=dt.date.today().isoformat(),
        help="Date to filter by (YYYY-MM-DD). Default: today (local).",
    )
    parser.add_argument(
        "--repos",
        nargs="*",
        default=DEFAULT_REPOS,
        help="Repos to check in OWNER/REPO format.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Maximum items to fetch per repo.",
    )
    parser.add_argument(
        "--no-proxy",
        action="store_true",
        help="Disable proxy env vars for gh calls.",
    )
    args = parser.parse_args()

    env = _clean_env(args.no_proxy)

    print(f"# Dify Daily Triage ({args.date})")
    print()
    print("Filters: open issues and open non-draft PRs created on the date above.")
    print()

    for repo in args.repos:
        print(f"## {repo}")

        issues = _gh_json(
            [
                "issue",
                "list",
                "-R",
                repo,
                "--state",
                "open",
                "--search",
                f"created:{args.date}",
                "--limit",
                str(args.limit),
                "--json",
                "number,title,createdAt,labels,url,closedByPullRequestsReferences",
            ],
            env,
        )

        prs = _gh_json(
            [
                "pr",
                "list",
                "-R",
                repo,
                "--state",
                "open",
                "--search",
                f"created:{args.date} draft:false",
                "--limit",
                str(args.limit),
                "--json",
                "number,title,createdAt,labels,url,isDraft,closingIssuesReferences",
            ],
            env,
        )

        issue_rows: list[list[str]] = []
        for issue in issues:
            issue_rows.append(
                [
                    "Issue",
                    str(issue.get("number")),
                    _escape_cell(issue.get("title", "")),
                    _escape_cell(_join_labels(issue.get("labels"))),
                    _escape_cell(
                        _linked_items(issue.get("closedByPullRequestsReferences"), "linked-pr")
                    ),
                    _escape_cell(issue.get("createdAt", "")),
                    f"[link]({issue.get('url')})",
                ]
            )

        pr_rows: list[list[str]] = []
        for pr in prs:
            if pr.get("isDraft"):
                continue
            pr_rows.append(
                [
                    "PR",
                    str(pr.get("number")),
                    _escape_cell(pr.get("title", "")),
                    _escape_cell(_join_labels(pr.get("labels"))),
                    _escape_cell(_linked_items(pr.get("closingIssuesReferences"), "linked-issue")),
                    _escape_cell(pr.get("createdAt", "")),
                    f"[link]({pr.get('url')})",
                ]
            )

        _print_table(
            "Issues",
            ["Type", "#", "Title", "Labels", "Link", "Created (UTC)", "URL"],
            issue_rows,
        )
        print()
        _print_table(
            "PRs",
            ["Type", "#", "Title", "Labels", "Link", "Created (UTC)", "URL"],
            pr_rows,
        )
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
