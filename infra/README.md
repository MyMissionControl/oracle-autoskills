# infra — host files the Oracle pipeline needs, which live outside every repo

These run the ψ → Oracle pipeline but sit in `~/.claude` and `~/.config/systemd`, so
nothing versioned them. A rebuilt or restored box silently loses them: the indexer stops
and search quietly degrades to whatever was already indexed, with no error anywhere.

| repo path | install to |
|---|---|
| `claude/bin/arra-mcp-capped.sh` | `~/.claude/bin/arra-mcp-capped.sh` (chmod +x) |
| `claude/oracle-psi-watcher.ts` | `~/.claude/oracle-psi-watcher.ts` |
| `claude/oracle-tenant-read.ts` | `~/.claude/oracle-tenant-read.ts` |
| `systemd/user/oracle-psi-watcher.service` | `~/.config/systemd/user/` |
| `systemd/user/oracle-psi-watcher.service.d/nice.conf` | `~/.config/systemd/user/oracle-psi-watcher.service.d/` |

Restore:

    cp -r infra/claude/.        ~/.claude/
    cp -r infra/systemd/user/.  ~/.config/systemd/user/
    chmod +x ~/.claude/bin/arra-mcp-capped.sh
    systemctl --user daemon-reload && systemctl --user enable --now oracle-psi-watcher

`arra-mcp-capped.sh` is also referenced by `mcpServers.arra-oracle-v3.command` in
`~/.claude.json`; the MCP fails to start if the path is missing.

**These copies drift.** Nothing syncs them back — after editing the live file, copy it here
and commit, or the backup silently describes an older system. Verify with `diff`.
