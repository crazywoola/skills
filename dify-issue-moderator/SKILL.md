---
name: dify-issue-moderator
description: Moderate GitHub issues for `langgenius/dify-plugins`, `langgenius/dify-official-plugins`, `langgenius/dify`, `langgenius/webapp-conversation`, and `langgenius/webapp-text-generator` with `gh` CLI. Use when asked to review an issue URL/number, close unclear issues, close issues written in Chinese, redirect question-type issues to forum/Discord, enforce Dify core issue standards from the bug template/contributing/code-of-conduct docs, and skip moderation for core or webapp issues opened by members or contributors.
---

# Dify Issue Moderator

## Overview
Moderate a single issue with deterministic checks and polite markdown replies.
Run the bundled script first in dry-run mode, then apply closure only after the decision is confirmed.
Always include a summary markdown table with columns: `issue id | decision | origin issue link`.

## Quick Start
### Prerequisites
- Authenticate GitHub CLI: `gh auth status`.
- Provide an issue URL, or provide issue number with `--repo owner/repo`.
- Use the bundled script from this skill folder.

### Workflow
1. Run a dry review:
   ```bash
   python3 scripts/moderate_issue.py --issue <ISSUE_URL_OR_NUMBER> [--repo <owner/repo>]
   ```
2. Read decision reasons and comment preview.
3. Apply moderation only when the decision is correct:
   ```bash
   python3 scripts/moderate_issue.py --issue <ISSUE_URL_OR_NUMBER> [--repo <owner/repo>] --apply
   ```
4. Verify issue state and posted comment on GitHub.

## Decision Rules

### Enterprise Requests
Close with a polite comment when the issue is related to the enterprise Helm chart or is an enterprise inquiry. Direct the reporter to business@dify.ai or Zendesk.

### Self Hosted (Source)
Close with a polite comment when the issue indicates it starts from source or lists the deployment type as **Self Hosted (Source)**. Include the required support policy text in the reply.

### Language Check Exception
When checking for Chinese/CJK text, ignore the following phrases if they appear inside the issue template **Self Checks** section:
- `I confirm that I am using English to submit this report (我已阅读并同意 Language Policy).`
- `[FOR CHINESE USERS] 请务必使用英文提交 Issue，否则会被关闭。谢谢！:)`
Only classify an issue as a language issue when the CJK ratio is **at least 20%** after applying the exception above.
Compute the CJK ratio as CJK codepoints divided by non-whitespace characters after applying the exception above.

### `langgenius/dify-plugins` and `langgenius/dify-official-plugins`
Close with a polite comment when:
- Issue title/body has CJK ratio **>= 20%**.
- Issue is a question rather than an actionable issue.
- Issue description is too unclear for contributors to understand or pick up.

### `langgenius/dify`, `langgenius/webapp-conversation`, and `langgenius/webapp-text-generator`
- Skip moderation when author association is `OWNER`, `MEMBER`, `COLLABORATOR`, or `CONTRIBUTOR`.
- Skip moderation when there is a linked PR (closing reference attached to the issue).
- For other authors, close with a polite comment when:
  - Issue title/body has CJK ratio **>= 20%** (English-only policy).
  - Issue is a question and should go to community support channels.
  - Issue is in `langgenius/dify` and the reported Dify version in the description is **below v1.10.0**. Tell them to upgrade to the latest version and retry before reopening.
  - Issue does not meet baseline standards from bug template/contributing/code-of-conduct docs.
  - Issue is plugin-related and should be filed in `langgenius/dify-official-plugins` using the plugin bug template.
 - Do not close feature requests that match these accepted patterns, even if they lack explicit "use case" keywords:
   - Feature request template is filled with a substantive story under "Is this request related to a challenge you're experiencing?" (not `_No response_`).
   - Includes concrete example input/output or expected behavior.
   - Clearly asks to add/support/allow/enable/expose/visualize/customize a feature and provides a detailed description (not just a short sentence).

### Plugin Bug Template
For plugin-related issues (especially when filed in `langgenius/dify`), direct reporters to use:
- `https://github.com/langgenius/dify-official-plugins/issues/new?template=bug_report.yml`

Load detailed criteria from `references/dify-issue-standards.md` when manual confirmation is needed.

## Reply Format Requirements
- Start with appreciation: `Hi @<user>, thanks for opening this issue.`
- Use short markdown sections:
  - `### Why this is being closed`
  - `### Next steps`
- Keep language respectful, neutral, and actionable.
- For enterprise Helm chart issues or enterprise inquiries, include:
  `Please reach out to our business@dify.ai or submit a report via Zendesk.`
- For issues that start from source or list **Self Hosted (Source)**, include:
  `We do not provide technical support for starting from the source. Thank you for your understanding. We assume you have the necessary expertise to set it up independently. If you require technical support, please obtain our business license by contacting us at business@dify.ai.`
- For security-related issues in `langgenius/dify`, add the following text verbatim to the response (preferably under `### Next steps`):
  ```
  First, if you believe this is a security-related issue, please submit it through a GitHub Advisory and please provide a complete proof of concept (PoC) 

  https://github.com/langgenius/dify/security/advisories/new
  ```
- For outdated version closures, explicitly ask them to upgrade to the latest release and retest before filing a new issue.
- For question issues, include:
  - `https://forum.dify.ai/`
  - `https://discord.com/invite/FngNHpbcY7`
- For plugin-related issues, include:
  - `https://github.com/langgenius/dify-official-plugins/issues/new?template=bug_report.yml`

## General Guide
- When contributors ask how to get started, load `references/dify-issue-standards.md` and use the "Get Your Hands Dirty" section.

## Command Reference
- Dry run (default):
  ```bash
  python3 scripts/moderate_issue.py --issue https://github.com/langgenius/dify-plugins/issues/123
  ```
- Issue number with repo:
  ```bash
  python3 scripts/moderate_issue.py --issue 123 --repo langgenius/dify
  ```
- Apply close action:
  ```bash
  python3 scripts/moderate_issue.py --issue 123 --repo langgenius/dify --apply
  ```

## Safety
- Always dry-run first.
- If classification is ambiguous, stop and request manual confirmation instead of applying closure automatically.
