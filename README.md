# Msty Local Ops

Msty Local Ops is a small, fail-closed MCP for Msty Studio on macOS. It exposes four
read-only diagnostics and, in a separate opt-in process, one bounded local-generation
tool. It does not read chats, Knowledge Stacks, private databases, provider keys, or
application configuration.

This is an independent community project, not an official Msty product.

## What you get

The default diagnostic process exposes exactly:

- `get_msty_status`
- `get_capability_manifest`
- `get_model_manifest`
- `run_compatibility_check`

The separate local-inference process adds only `local_generate`. That tool requires
an exact model identifier advertised by a fixed Msty loopback service. It never
auto-selects a model, follows redirects, uses a proxy, or falls back to an online
provider.

## Install

1. Install [Msty Studio for macOS](https://msty.ai/products/studio/).
2. Install Python 3.10, 3.11, or 3.12. The installer selects a supported version even
   when a newer `python3` is also installed.
3. Download this repository and double-click `Install Msty Local Ops.command`.
4. The installer creates two ready-to-paste Toolbox JSON files and opens their folder.
5. In Msty Studio, open **Toolbox → Add New Tool → STDIO / JSON** and paste the
   diagnostic JSON first.
6. Test the tool in Msty's Tool Console before attaching it to a conversation.

Msty's official Toolbox guide explains the same local STDIO/JSON flow:
[Msty Studio Tools](https://docs.msty.ai/studio/toolbox/tools).

The diagnostic MCP is the safe default. Add the local-inference JSON only when you
want the calling model to send prompts to a local Msty model. The calling MCP client
can observe those prompts and results; see [PRIVACY.md](PRIVACY.md).

## Try the fictional Knowledge Stack

The folder `examples/knowledge-stack/synthetic-canary` contains a completely
fictional retrieval test. It includes a controlling handbook, an obsolete source, an
incident clarification, and an adversarial note.

1. In Msty, create a Knowledge Stack.
2. Add the entire `synthetic-canary` folder.
3. Choose a local embedding model if you want processing to remain on the device.
4. Compose the stack and attach it to a chat using a local model.
5. Run the questions in [docs/KNOWLEDGE_STACK.md](docs/KNOWLEDGE_STACK.md).

Official references:
[Knowledge Stack basics](https://docs.msty.app/features/knowledge-stack/basics) and
[local embeddings](https://docs.msty.app/features/knowledge-stack/embeddings).

## Network and data boundary

The adapter has only these destinations:

| Msty service | Address |
|---|---|
| Local AI | `127.0.0.1:11964` |
| MLX | `127.0.0.1:11973` |
| llama.cpp | `127.0.0.1:11454` |

Only `GET /v1/models` and `POST /v1/chat/completions` are permitted. The default
diagnostic process never submits prompts.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/python scripts/check_public_boundary.py .
uv lock --check
uv export --frozen --no-dev --no-emit-project --format requirements.txt --output-file requirements-audit.txt
```

The public repository must start with a fresh initial commit. Do not merge or import
history from an operational or private repository.

## License and attribution

MIT licensed. See [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md).
