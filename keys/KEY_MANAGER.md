# Key Manager

## Principles
- No secrets in repo
- Credentials via env/credential broker only
- Adapters injected at runtime
- SSH keys from persistent location (~/.ssh)
- gh CLI uses existing auth

## Integration
- GitHub: SSH (existing)
- Cloud: via env vars injected at runtime
- MCP: per-server auth via broker
