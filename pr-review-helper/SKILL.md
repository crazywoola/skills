---
name: pr-review-helper
description: Review Dify plugin pull requests end-to-end. Use when asked to read a PR URL/number, run local checks equivalent to .github/workflows/pre-check-plugin.yaml, enforce English-only PR content (while ignoring the fixed bilingual notice sentence `【中文用户 & Non English User】请使用英语提交，否则会被关闭 ：）` and skipping Chinese checks in the PR `Self Checks` section for `langgenius/dify-plugins` and `langgenius/dify-official-plugins`), enforce that each plugin README.md contains no Chinese characters (with multilingual README docs linked on failure), verify dify_plugin version at least 0.5.0, clean up checked-out PR branches after checks, and submit a GitHub review decision (approve with LGTM on pass, request changes with detailed markdown findings on issues).
---

# PR Review Helper

## Overview
Run deterministic PR review checks for `langgenius/dify-plugins` and submit the final review through `gh`.
Output local check results in readable markdown sections/tables.
Always include a summary markdown table in your response to the user with columns: `issue link | decision`.
If no issue link is available, use the PR link and note it in the analysis.
Use emoji to represent status (for example, `✅ pass` and `❌ no pass`) and keep all output GitHub-flavored Markdown so it renders correctly on GitHub.

## Scope Guardrails
- Skip this skill when the task is **issue moderation** (not PR review).
- For `langgenius/dify-plugins` and `langgenius/dify-official-plugins` issues, skip if issue author association is `MEMBER` or `CONTRIBUTOR`.
- Use `dify-issue-moderator` for issue moderation flows.

## Workflow
1. Confirm this task is PR review (not issue moderation). If it is issue moderation in plugin repos and author is `MEMBER` or `CONTRIBUTOR`, skip this skill.
2. Request a PR URL or PR number when missing.
3. Run `scripts/review_pr.py` from the repository root.
4. Let the script collect PR metadata, check out the PR branch, and run local pre-check logic matching `.github/workflows/pre-check-plugin.yaml`.
5. Let the script validate PR title/body language, ignore the fixed bilingual notice sentence `【中文用户 & Non English User】请使用英语提交，否则会被关闭 ：）`, and skip Chinese checks in the PR `Self Checks` section for `langgenius/dify-plugins` and `langgenius/dify-official-plugins`.
6. Let the script unpack the changed `.difypkg` and fail if `README.md` contains any Chinese characters.
7. Let the script verify `dify_plugin>=0.5.0` in the test environment.
8. Let the script switch back to the original branch and delete the checked-out PR branch after checks complete.
9. Submit review with `gh pr review`:
   - Approve with `LGTM` only when all checks pass.
   - Request changes with highlighted markdown sections and tables otherwise.
10. In the review comment to the plugin author, include a compact status table listing each check/action with an emoji + `pass`/`no pass` status and a `required action` column, followed by a clear `Next steps` section.
11. In your response to the user, include the required summary table and a short analysis (2-4 sentences) explaining the decision and any notable failures. Use emoji in the decision/status cell and ensure GitHub-flavored Markdown rendering (proper table headers and separators, no raw HTML).

## Commands
Use this as the default command:

```bash
python3 scripts/review_pr.py --pr <PR_URL_OR_NUMBER> --submit-review
```

Useful options:

- `--repo <owner/repo>`: Override repository (default `langgenius/dify-plugins`).
- `--pr-content-max-cjk <int>`: Maximum allowed Chinese/CJK in PR title/body after allowlist filtering (default `0`).
- `--allow-pr-cjk-snippet <text>`: Extra allowlisted PR snippet containing CJK (repeatable). Default allowlist includes `【中文用户 & Non English User】请使用英语提交，否则会被关闭 ：）`.
- `--readme-max-cjk <int>`: Maximum allowed Chinese/CJK characters in `README.md` (default `0`).
- `--approve-message <text>`: Approval body text (default `LGTM`).
- `--keep-temp`: Keep temporary artifacts for debugging.

## Review Standard
Approve only if all of these pass:

1. Exactly one `.difypkg` file changed in the PR.
2. PR title/body contains no Chinese characters except the allowlisted sentence `【中文用户 & Non English User】请使用英语提交，否则会被关闭 ：）`, and the PR `Self Checks` section is excluded from Chinese checks for `langgenius/dify-plugins` and `langgenius/dify-official-plugins`.
3. Manifest author does not contain `langgenius` or `dify`.
4. Plugin icon exists and is not a default/template icon.
5. Plugin version is not already published on marketplace.
6. Dependency/install/packaging checks succeed locally.
7. `dify_plugin` version is at least `0.5.0`.
8. Plugin `README.md` contains no Chinese characters.

## Failure Handling
When any check fails:

1. Use `REQUEST_CHANGES`.
2. Format the review comment using markdown headings and a status table.
3. Include each failed check with concrete details and an action request to update and push fixes.
4. When `README.md` fails language check, include this doc link in the review comment: `https://docs.dify.ai/en/develop-plugin/features-and-specs/plugin-types/multilingual-readme#multilingual-readme`.
5. Ensure the status table uses `pass`/`no pass` and includes a `required action` column plus a `Next steps` section.
   - Status cells must include emoji (for example, `✅ pass` or `❌ no pass`) while retaining the text.

## Prerequisites
Run in a repo clone with:

- `gh` authenticated
- `python3`
- `jq`
- `unzip`
- network access (for toolkit clone, daemon download, marketplace API)
