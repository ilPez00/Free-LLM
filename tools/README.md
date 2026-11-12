# Free-LLM local tools

This clone of [nejib1/Free-LLM](https://github.com/nejib1/Free-LLM) carries two
local additions on top of the upstream data repo (upstream has no runnable
code — it is a provider directory and code examples):

```
providers.json          machine-readable catalog built from README.md
tools/build_catalog.py  rebuilds providers.json from the README tables
tools/free-llm          CLI: list / show / models / opencode / check
```

## Catalog

`providers.json` is regenerated from the README (Quick Reference + the
Permanent / Renewable / Trial tables) and from each provider's
`code-examples/<slug>/curl.sh`:

```sh
python3 tools/build_catalog.py          # writes providers.json
```

Each record has: `slug`, `name`, `categories`, `card_required`, `base_url`,
`key_url`, `models`, `example_model`, `openai_compatible`, limits, and a link
to the provider's `code-examples/` directory.

## CLI

`free-llm` is on `PATH` via `~/bin/free-llm`.

```sh
free-llm list [--category permanent|renewable|trial] [--openai-compatible]
free-llm show groq-cloud
free-llm models groq-cloud
free-llm opencode groq-cloud --key-env GROQ_API_KEY   # provider JSON snippet
free-llm check groq-cloud                             # live completion probe
```

### Key resolution

`check` and `opencode` look for a key in this order:

1. the process environment (`--key-env NAME` to force a name)
2. `~/.env` — the last **non-empty** assignment for that name

Candidate names are derived from the provider name/slug plus a curated alias
map (`PROVIDER_KEY_ALIASES` in `tools/free-llm`), so `z-ai` looks for
`Z_AI_API_KEY` / `AI_ZHIPU_KEY` and never borrows an unrelated provider's key.
Keys are never printed; the source label (`GROQ_API_KEY` or
`~/.env:GROQ_API_KEY`) is.

`check` posts a one-line completion through `curl` (some providers' edges block
`urllib`'s TLS fingerprint) and reports `HTTP <status> | OK/FAIL`.

## OpenCode

`free-llm opencode <slug>` emits a provider block for `opencode.json`. Keys are
referenced as `{env:NAME}`, which OpenCode resolves from the **server**
environment — on this host the long-running `opencode serve --service` process
inherits `~/.zshenv`, not `~/.env`, so a key must be exported there (or the
server restarted) before an `{env:...}` provider works.

A `groq` provider block was added to `~/.config/opencode/opencode.json`
(backup: `opencode.json.bak-freellm-*`). It authenticates correctly, but
Groq's free tier caps at 8K tokens/minute while OpenCode sends ~29K tokens of
system prompt + tools, so OpenCode sessions on `groq/*` fail with a TPM error.
Groq remains usable through `free-llm check`, `curl`, or any client that sends
a small context.

## Notes

- Upstream README tables are regenerated nightly from the free-llm.com
  database; re-run `build_catalog.py` after a `git pull` to refresh.
- `providers.json` and `tools/` are local additions, not part of upstream.
