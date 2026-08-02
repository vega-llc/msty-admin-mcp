# Security policy

## Supported surface

Only the four-tool diagnostic server and the separate five-tool local-inference
server are supported. The local-inference server must be added explicitly.

## Reporting a vulnerability

When the repository is published, use its private GitHub security-advisory form.
Do not place credentials, private documents, prompts, or machine-specific evidence
in a public issue.

## Design constraints

- fixed loopback destinations only
- no HTTP redirects or proxy use
- no database or credential access
- no remote transport
- no automatic model selection
- no cloud fallback
- no simulated success responses
- bounded inputs, inventory, metadata, and response sizes
