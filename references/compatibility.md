# Agent host compatibility

This package follows the open Agent Skills directory shape: a `SKILL.md` entrypoint plus optional `scripts/` and `references/`. The client itself is host-neutral and uses only Python 3 standard-library modules.

## Minimum host capabilities

The host must be able to:

1. Discover or be instructed to read `SKILL.md`.
2. Read user-provided local files.
3. Run Python 3 scripts.
4. Make outbound HTTPS requests to the configured API host.
5. Return plain text or a generated local file to the user.

If a product does not support Agent Skills, local scripts, file access, or outbound HTTPS, copying this folder alone cannot add those capabilities. Adapt the same workflow to that product's plugin, MCP, extension, or automation format.

## Installation guidance

- For hosts supporting the Agent Skills open format, install the complete `article-rewriter` directory in that host's user-level skills directory.
- For repository-scoped use, place the complete directory in the host's repository skills location.
- Keep relative paths intact; `SKILL.md` expects `scripts/rewrite_article.py` and the two references beside it.
- On first use, `config-status` creates `config.yaml` under the current user's application configuration directory. Configure that file separately on every machine. Never distribute a populated config file with the skill.

The service endpoint is intentionally internal to the client rather than exposed in the user configuration. Never embed a customer or upstream API Key in the distributed package.
