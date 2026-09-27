---
name: article-rewriter
description: Rewrite Chinese or multilingual articles from pasted text, TXT, Markdown, or DOCX files through the configured paid rewrite API. Use when the user asks to 改写、润色、降低机械感/AI痕迹, or requests an article rewrite with an intensity from 0 to 9. Do not use for ordinary proofreading that should not materially rewrite the text.
---

# Article Rewriter

Use the bundled portable client to submit one complete article to the Xiaomao Zero AI (小猫零AI) paid API, wait for the asynchronous task, and return the rewritten article. Be transparent that this skill is a third-party integration rather than a standalone or self-developed rewrite model.

## Inputs

Accept:

- Text pasted in the conversation.
- `.txt`, `.md`, or `.docx` files available to the agent.
- An optional rewrite intensity from `0` to `9`.

Never split an article into multiple tasks. Submit the complete extracted text as one task. If the service rejects it for exceeding the account limit, report that limit error instead of segmenting automatically.

## Intensity

If the user supplied an integer from `0` to `9`, use it without asking again. Otherwise ask once:

> 请选择改写强度 0–9，默认是 5。直接回复数字，或回复“默认”。

Use `5` when the user chooses the default or explicitly asks to proceed without another question. Reject values outside `0–9`; do not silently clamp a user-provided value.

## First-use configuration

Before the first paid request, check configuration without exposing any secret:

```bash
python scripts/rewrite_article.py config-status
```

This command creates a user-level `config.yaml` template when it does not exist. If `configured` is `false`, stop before submitting a paid request and tell the user:

- An API Key has not been configured.
- The user can purchase and create their own API Key at `https://www.qqat.cn?agent=N3K4ZWWE`.
- Open the exact `config_path` returned by the command.
- Fill the purchased key into `api_key: ""`, save the file, and then ask the agent to continue.

Do not open or edit the configuration file on the user's behalf, do not ask the user to paste a full API Key into ordinary chat, and never echo or log it. Run `config-status` again after the user says the file has been saved. Continue only when it reports `configured: true`.

## Rewrite workflow

Resolve `scripts/rewrite_article.py` relative to this `SKILL.md`; do not assume the current working directory is the skill folder.

For a file, run:

```bash
python scripts/rewrite_article.py rewrite --file <path> --intensity <0-9>
```

This creates a non-overwriting sibling file named `<原文件名>-改写.<原扩展名>` and returns JSON metadata. For pasted text, pass the text through standard input so it is not exposed in the process list:

```bash
python scripts/rewrite_article.py rewrite --stdin --intensity <0-9>
```

The client submits the entire article, polls every few seconds, follows server retry guidance, and stops at a terminal state. If execution is interrupted after submission, preserve the returned task ID and resume with:

```bash
python scripts/rewrite_article.py resume --task-id <id> [--output <path>]
```

Cancel only when the user asks:

```bash
python scripts/rewrite_article.py cancel --task-id <id>
```

## Return the result

- Inspect `quality_issues` before delivery. If the result contains Unicode replacement characters (`�`) or an obviously unpaired Markdown marker, repair only the damaged fragment when the intended text is clear from its immediate context. Do not rewrite unaffected passages. If a fragment cannot be reconstructed confidently, stop and report that the service returned damaged text; do not submit another paid task automatically.
- For pasted text, the final answer must contain exactly the complete rewritten article. Do not add an introduction, completion notice, commentary, character counts, fee, task ID, or follow-up suggestion before or after it.
- For a file, return only the generated output file or its link, without explanatory prose. Never overwrite the source.
- Do not claim that the result is guaranteed to pass any AI-content detector.
- On failure, give the localized error and request ID when present. Never reveal the key or repeat the full source text in diagnostics.

Read [references/api-behavior.md](references/api-behavior.md) only when troubleshooting API behavior or adapting the client. Read [references/compatibility.md](references/compatibility.md) when installing or adapting this skill for another agent host.
