---
name: gh-dify-daily-triage
description: GitHub triage for langgenius/dify, langgenius/dify-plugins, langgenius/dify-official-plugins, langgenius/webapp-conversation, langgenius/webapp-text-generator, langgenius/dify-docs, and langgenius/dify-plugin-daemon using the gh CLI. Use when asked to list issues and PRs created today (or in a given time range) that are open (non-draft PRs), show whether each issue has a linked PR or each PR has a linked issue, format results as Markdown tables without author/state columns and with clickable URLs, and provide attention analysis.
---

# GH Dify Daily Triage

## Overview
Generate a triage report for Dify GitHub repos with open issues and open non-draft PRs created on a single date or within a date range, formatted as Markdown tables plus a short attention analysis.

## Workflow
1. Run the data script to fetch issues and PRs for the target date or range.
2. Verify filters: issues must be `open`; PRs must be `open` and `draft:false`.
3. Present tables per repo (Issues, PRs). Do not include author or state columns. URLs must be clickable Markdown links.
4. Add an **Attention** section highlighting what needs action.

## Run The Script
Use the bundled script to fetch and format data.

```bash
python /Users/crazywoola/.claude/skills/gh-dify-daily-triage/scripts/dify_daily_triage.py
```

Optional flags:
- `--date YYYY-MM-DD` to query a single day (default: today).
- `--since YYYY-MM-DD` start of a date range (overrides `--date`).
- `--until YYYY-MM-DD` end of a date range (default: today when `--since` is set).
- `--repos owner/repo ...` to override the repo list.
- `--no-proxy` if `gh` fails due to local proxy settings.

Examples:
```bash
# Single day
python /Users/crazywoola/.claude/skills/gh-dify-daily-triage/scripts/dify_daily_triage.py --date 2026-02-05

# Date range (last 7 days)
python /Users/crazywoola/.claude/skills/gh-dify-daily-triage/scripts/dify_daily_triage.py --since 2026-02-24 --until 2026-03-02

# Since a date until today
python /Users/crazywoola/.claude/skills/gh-dify-daily-triage/scripts/dify_daily_triage.py --since 2026-02-24
```

## Output Format Rules
- Produce sections per repo: `## repo`, then `### Issues` and `### PRs`.
- Table columns (no author/state columns): `Type`, `#`, `Title`, `Labels`, `Link`, `Created (UTC)`, `URL`.
- URL column must be clickable, e.g. `[link](https://github.com/...)`.
- Link column labels:
  - Issues: `linked-pr: [#123](...)` or `no-linked-pr`.
  - PRs: `linked-issue: [#123](...)` or `no-linked-issue`.

## Attention Analysis Heuristics
Call out items that need attention:
- Security or vulnerability keywords in title/labels (`security`, `vulnerability`, `ssrf`, `cve`, `rce`).
- Open bugs with **no linked PR** (likely unassigned or awaiting fix).
- Open PRs with **no linked issue** (ask for issue linkage or rationale).
- Large change labels (`size:XL`, `size:XXL`) or risky areas (e.g., `web`, infra).
- Issues labeled `good first issue` or `status: accepting prs` (good to delegate).
- Anything urgent, customer-facing, or cloud-related (labels like `cloud`).

## Troubleshooting
- If `gh` fails, confirm authentication with `gh auth status`.
- If requests fail through a proxy, rerun with `--no-proxy`.

## Manual Fallback (if script is unavailable)
Use `gh` directly with the same filters (repeat per repo).

For a single day use `created:YYYY-MM-DD`; for a range use `created:YYYY-MM-DD..YYYY-MM-DD`:

```bash
# Single day
gh issue list -R langgenius/dify --state open --search "created:2026-03-02" --json number,title,createdAt,labels,url,closedByPullRequestsReferences
gh pr list -R langgenius/dify --state open --search "created:2026-03-02 draft:false" --json number,title,createdAt,labels,url,isDraft,closingIssuesReferences

# Date range
gh issue list -R langgenius/dify --state open --search "created:2026-02-24..2026-03-02" --json number,title,createdAt,labels,url,closedByPullRequestsReferences
gh pr list -R langgenius/dify --state open --search "created:2026-02-24..2026-03-02 draft:false" --json number,title,createdAt,labels,url,isDraft,closingIssuesReferences
```

Repeat for the other repos and format the tables using the same rules above.
