---
name: dify-issue-moderator
description: Moderate GitHub issues for `langgenius/dify-plugins`, `langgenius/dify-official-plugins`, `langgenius/dify`, `langgenius/webapp-conversation`, and `langgenius/webapp-text-generator` with `gh` CLI. Use when asked to review an issue URL/number, close unclear issues, close issues violating language policy, redirect questions to forum/Discord, and enforce Dify issue standards.
---

# Dify Issue Moderator

Moderate a single GitHub issue with deterministic checks and polite markdown replies.

## Prerequisites

- `gh auth status` must pass.
- Provide an issue URL, or issue number with `--repo owner/repo`.

## Language Policy (All Repos)

**English only.** Close any issue or PR whose title/body violates this policy.

### How to measure

1. Strip these template phrases before counting (they are allowed):
   - `I confirm that I am using English to submit this report (我已阅读并同意 Language Policy).`
   - `[FOR CHINESE USERS] 请务必使用英文提交 Issue，否则会被关闭。谢谢！:)`
2. Compute **CJK ratio** = CJK codepoints / non-whitespace characters.
3. **Close if CJK ratio >= 20%.**

This policy applies equally to issues and PRs across all repos listed above.

## Decision Rules

### Skip moderation when

- **Core/webapp repos only** (`langgenius/dify`, `langgenius/webapp-conversation`, `langgenius/webapp-text-generator`): author association is `OWNER`, `MEMBER`, `COLLABORATOR`, or `CONTRIBUTOR`.
- Issue has a linked PR (closing reference).

### Close when

| Condition | Applies to | Action |
|---|---|---|
| CJK ratio >= 20% | All repos | Close — language policy |
| Question, not actionable issue | All repos | Close — redirect to forum/Discord |
| Description too unclear to act on | All repos | Close — ask to clarify and reopen |
| Enterprise / Helm chart inquiry | All repos | Close — redirect to business@dify.ai / Zendesk |
| Self Hosted (Source) deployment | All repos | Close — no source support |
| Dify version below v1.10.0 | `langgenius/dify` | Close — ask to upgrade and retest |
| Doesn't meet bug template standards | Core/webapp repos | Close — link to template |
| Plugin-related issue filed in wrong repo | `langgenius/dify` | Close — redirect to `dify-plugins` or `dify-official-plugins` |

For plugin routing in `langgenius/dify`:
- Redirect **custom/community plugin**, plugin SDK, `.difypkg`, `manifest.yaml`, or plugin daemon issues to `langgenius/dify-plugins`.
- Redirect **Dify-maintained model/tool/provider plugin** issues to `langgenius/dify-official-plugins`.
- If the report is clearly plugin-related but the exact destination is ambiguous, close it in `langgenius/dify` and provide both repo links.

### Do NOT close feature requests that

- Fill in the feature request template with a substantive story (not `_No response_`).
- Include concrete example input/output or expected behavior.
- Clearly ask to add/support/enable a feature with detailed description.

## Reply Format

Start every reply with: `Hi @<user>, thanks for opening this issue.`

Use two markdown sections:
- `### Why this is being closed`
- `### Next steps`

Keep language respectful, neutral, and actionable.

### Closing snippets by reason

**Language policy:**
> Please resubmit in English per our language policy.

**Question issue:**
> - https://forum.dify.ai/
> - https://discord.com/invite/FngNHpbcY7

**Enterprise / Helm chart:**
> Please reach out to our business@dify.ai or submit a report via Zendesk.

**Self Hosted (Source):**
> We do not provide technical support for starting from the source. Thank you for your understanding. We assume you have the necessary expertise to set it up independently. If you require technical support, please obtain our business license by contacting us at business@dify.ai.

**Outdated version:**
> Please upgrade to the latest release and retest before filing a new issue.

**Plugin-related issue in wrong repo:**
> If this is about a custom/community plugin, plugin SDK, packaging, or plugin daemon, please open it at https://github.com/langgenius/dify-plugins/issues/new
>
> If this is about a Dify-maintained model/tool/provider plugin, please open it at https://github.com/langgenius/dify-official-plugins/issues/new

**Security issue** (add verbatim under `### Next steps` in `langgenius/dify`):
> First, if you believe this is a security-related issue, please submit it through a GitHub Advisory and please provide a complete proof of concept (PoC)
>
> https://github.com/langgenius/dify/security/advisories/new

## Commands

```bash
# Dry run (default)
python3 scripts/moderate_issue.py --issue https://github.com/langgenius/dify-plugins/issues/123

# Issue number with repo
python3 scripts/moderate_issue.py --issue 123 --repo langgenius/dify

# Apply close action
python3 scripts/moderate_issue.py --issue 123 --repo langgenius/dify --apply
```

## Safety

- Always dry-run first.
- If classification is ambiguous, stop and ask for manual confirmation.
- Always output a summary table: `issue id | decision | origin issue link`.

## References

- Load `references/dify-issue-standards.md` for detailed criteria or contributor onboarding.
