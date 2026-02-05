# Dify Issue Moderation Standards

## Source Documents
- Bug report template:
  - https://github.com/langgenius/dify/blob/3aecceff27c6b712628ad463c6e6ac15b8527ebe/.github/ISSUE_TEMPLATE/bug_report.yml
- Code of Conduct (includes language policy):
  - https://github.com/langgenius/dify/blob/4c1ad40f8e8a6ee58a958330558f2178b7e47fa7/.github/CODE_OF_CONDUCT.md
- Contributing guide:
  - https://github.com/langgenius/dify/blob/25ac69afc5ac9324079be5f0d02b2a2b03dcc784/CONTRIBUTING.md

## Repositories Covered
- `langgenius/dify-plugins`
- `langgenius/dify-official-plugins`
- `langgenius/dify`

## Plugin Repositories Rules
Close the issue with a polite markdown comment when any of these is true:

1. Title or description has CJK ratio **>= 20%**.
   - Exception: Ignore Chinese text in the **Self Checks** section when it is only one of these template phrases:
     - `I confirm that I am using English to submit this report (我已阅读并同意 Language Policy).`
     - `[FOR CHINESE USERS] 请务必使用英文提交 Issue，否则会被关闭。谢谢！:)`
2. Issue is a usage/support question instead of an actionable issue.
3. Issue is unclear (too short, placeholder content, or insufficient context for triage).

For question issues, redirect users to:
- https://forum.dify.ai/
- https://discord.com/invite/FngNHpbcY7

## Core Repository Rules (`langgenius/dify`)

### Skip Conditions
Do not moderate when issue author association is:
- `OWNER`
- `MEMBER`
- `COLLABORATOR`
- `CONTRIBUTOR`
Do not moderate when the issue has a linked PR (closing reference attached to the issue).

### Enforced Baseline
For other authors, close with a polite comment when any of the following applies:

1. Non-English issue content (CJK ratio **>= 20%**).
   - Exception: Ignore Chinese text in the **Self Checks** section when it is only one of these template phrases:
     - `I confirm that I am using English to submit this report (我已阅读并同意 Language Policy).`
     - `[FOR CHINESE USERS] 请务必使用英文提交 Issue，否则会被关闭。谢谢！:)`
2. Question-style issue (not actionable bug/task report).
3. Reported Dify version in the description is below `v1.10.0`. Ask the reporter to upgrade to the latest release and retest.
4. Missing essential issue quality information.

Do not close feature requests that match these accepted patterns (even if they do not contain explicit "use case" keywords):
- Feature request template is filled with a substantive story under the "Is this request related to a challenge you're experiencing?" section (not `_No response_`).
- Includes concrete example input/output or expected behavior.
- Clearly asks to add/support/allow/enable/expose/visualize/customize a feature and provides a detailed description.

### Essential Quality Information
For bug-like reports, verify presence of:
- Dify version
- Deployment mode (Cloud or Self Hosted)
- Steps to reproduce
- Expected behavior
- Actual behavior and logs/error details (strongly expected)

Also verify:
- Title is descriptive (not generic like "bug" or "help")
- Description is detailed enough to reproduce or assess
- Language and tone are respectful and professional

For feature-like reports, verify:
- Clear use case/scenario and expected value

## Comment Style
Every close comment should:
- Start with appreciation (`Hi @user, thanks...`)
- Use short sections (`### Why this is being closed`, `### Next steps`)
- Explain exactly what is missing/wrong in neutral language
- Provide actionable next steps and destination links when needed

## Get Your Hands Dirty
Want to dive in and contribute? Here is how to get started:

- Read the contributing guide: https://github.com/langgenius/dify/blob/main/CONTRIBUTING.md
- Browse good first issues: https://github.com/langgenius/dify/issues?q=is%3Aissue%20state%3Aopen%20label%3A%22good%20first%20issue%22
- Add a new model runtime or tool by opening a PR in: https://github.com/langgenius/dify-plugins
- Update existing runtimes/tools or fix plugin bugs in: https://github.com/langgenius/dify-official-plugins
- Link an existing issue or open a new issue in the PR description.
