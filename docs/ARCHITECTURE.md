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
