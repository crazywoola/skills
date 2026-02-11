---
name: pr-review-helper
description: Review Dify plugin pull requests end-to-end. Use when asked to read a PR URL/number, run local checks equivalent to .github/workflows/pre-check-plugin.yaml, enforce English-only PR content (while ignoring the fixed bilingual notice sentence `【中文用户 & Non English User】请使用英语提交，否则会被关闭 ：）` and skipping Chinese checks in the PR `Self Checks` section for `langgenius/dify-plugins` and `langgenius/dify-official-plugins`), enforce that each plugin README.md contains no Chinese characters (with multilingual README docs linked on failure), verify PRIVACY.md exists, verify dify_plugin version at least 0.5.0, clean up checked-out PR branches after checks, and submit a GitHub review decision (approve with LGTM on pass, request changes with detailed markdown findings on issues).
---

# PR Review Helper

Review plugin PRs for `langgenius/dify-plugins` and `langgenius/dify-official-plugins`, run local pre-checks, and submit the review via `gh`.

## Scope

- **PR review only.** Skip if the task is issue moderation — use `dify-issue-moderator` instead.
- Skip if the PR author association is `MEMBER` or `CONTRIBUTOR` in plugin repos.

## Workflow

1. Get PR URL or number.
2. Run the review script (dry-run by default):
   ```bash
   python3 scripts/review_pr.py --pr <PR_URL_OR_NUMBER> --submit-review
   ```
3. The script does everything: fetch metadata → checkout PR → unpack `.difypkg` → validate structure → run checks → switch back → clean up branch.
4. Submit review via `gh pr review`:
   - **All pass** → Approve with `LGTM`.
   - **Any fail** → Request changes with a status table and required fixes.
5. Respond to the user with a summary table (`issue link | decision`) and a short analysis.

## Approval Checklist

All must pass:

| # | Check | Rule |
|---|---|---|
| 1 | **Single .difypkg** | Exactly one `.difypkg` file changed in the PR |
| 2 | **PR language** | No CJK in title/body (except allowlisted bilingual notice `【中文用户 & Non English User】请使用英语提交，否则会被关闭 ：）`; Self Checks section excluded) |
| 3 | **Project structure** | `manifest.yaml`, `README.md`, `PRIVACY.md`, `_assets/` all present |
| 4 | **Manifest author** | Must not contain `langgenius` or `dify` |
| 5 | **Icon** | Exists, not default/template |
| 6 | **Version** | Not already published on marketplace |
| 7 | **README language** | No Chinese characters ([multilingual docs](https://docs.dify.ai/en/develop-plugin/features-and-specs/plugin-types/multilingual-readme#multilingual-readme)) |
| 8 | **PRIVACY.md** | Must exist and be non-empty |
| 9 | **Dependencies** | `pip install -r requirements.txt` succeeds |
| 10 | **dify_plugin version** | `>= 0.5.0` |
| 11 | **Install test** | `test-plugin-install.py` passes |
| 12 | **Packaging test** | `upload-package.py --test` passes |

## Failure Format

When requesting changes, the review comment must include:
- A status table with emoji (`✅ Pass` / `❌ Fail`) and a `Required action` column.
- A `### Next steps` section listing what to fix.
- The multilingual README doc link when README language fails.

## Options

| Flag | Default | Description |
|---|---|---|
| `--repo` | `langgenius/dify-plugins` | Target repository |
| `--pr-content-max-cjk` | `0` | Max CJK chars allowed in PR content |
| `--readme-max-cjk` | `0` | Max CJK chars allowed in README.md |
| `--allow-pr-cjk-snippet` | bilingual notice | Extra allowlisted CJK snippet (repeatable) |
| `--approve-message` | `LGTM` | Approval body text |
| `--keep-temp` | off | Keep temp artifacts for debugging |

## Prerequisites

`gh` (authenticated), `python3` (≥ 3.11), `jq`, `unzip`, network access.
