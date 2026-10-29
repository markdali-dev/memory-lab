"""Run one of the project's agents headless and show its answer plus cost.

    python3 scripts/run_agent.py analyst "Who were our top 5 customers last year?"
    python3 scripts/run_agent.py memory-manager "Review the pending proposals."

Uses `claude -p --agent <name>`, so the agent's own tool list (in
.claude/agents/<name>.md) limits what it can do. Runs on your Claude Code
login: no API key needed.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(agent, prompt):
    cmd = ["claude", "-p", prompt, "--agent", agent,
           "--mcp-config", ".mcp.json", "--strict-mcp-config",
           "--allowedTools", "mcp__memlab",
           "--output-format", "json"]
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=900)
    if out.returncode != 0 and not out.stdout:
        raise SystemExit(out.stderr)
    return json.loads(out.stdout)


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    r = run(sys.argv[1], sys.argv[2])
    u = r.get("usage", {})
    tokens_in = u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
    print(r.get("result", ""))
    print(f"\n--- {sys.argv[1]}: {r.get('num_turns')} turns, "
          f"{tokens_in:,} input tokens, {u.get('output_tokens', 0):,} output tokens, "
          f"{r.get('duration_ms', 0) / 1000:.0f}s")


if __name__ == "__main__":
    main()
