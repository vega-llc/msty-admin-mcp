# Privacy boundary

Msty Local Ops has no telemetry, analytics, hosted service, credential store, or
configurable network destination.

The modern adapter can contact only Msty's three fixed loopback model endpoints on
`127.0.0.1`. It disables HTTP proxies and redirects. It does not read Msty's private
database, chats, Knowledge Stacks, provider credentials, or application settings.

An MCP client can see every argument passed to a tool and every result returned by
that tool. Do not send sensitive content through the local-inference tool unless the
calling MCP client is also trusted to receive it. For private document work, attach
the documents directly to a local model in Msty and independently verify that no
online model, remote embedding, web feature, tool, or fallback is enabled.

This project cannot attest to the privacy settings of Msty, a selected model, an MCP
client, the operating system, or any separately configured provider.
