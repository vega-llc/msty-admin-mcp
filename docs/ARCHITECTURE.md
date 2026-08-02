# Architecture

```text
MCP client
  ├─ diagnostics process: four read-only tools
  └─ optional local-inference process: the same four tools + local_generate
                         │
                         └─ fixed loopback-only Msty endpoints
```

The two processes register their tools directly. Environment variables cannot enlarge
the tool surface or change the destination host and ports. Inventory and generation
requests have strict size, schema, and timeout bounds. HTTP proxy use and redirects
are disabled.

The MCP does not manage Msty. It reports what the fixed local endpoints advertise and
can submit one explicit local-generation request. It does not modify models, projects,
providers, tools, chats, Knowledge Stacks, or application settings.

The separate doctor CLI reads the public app bundle metadata, process state, and the
same fixed loopback model-list endpoints. Its upgrade fingerprint contains only the
adapter version, Studio version, service booleans, and model counts. The support CLI
projects those facts into a smaller redacted schema and never serializes raw errors,
paths, process identifiers, model identifiers, provider settings, prompts, or content.
