"""MCP server: exposes the memory store and the database as tools.

MCP (Model Context Protocol) is a standard way for an AI app to call
outside tools. This server speaks it over stdio: the AI app starts this
script, sends one JSON-RPC message per line on stdin, and reads one reply
per line from stdout. Written without the MCP SDK so every step is visible.

The messages that matter:
  initialize   -> say who we are and that we offer tools
  tools/list   -> describe each tool (name, description, input schema)
  tools/call   -> run a tool and return its result as text

Run by an MCP client (see .mcp.json), not by hand.
"""

import json
import os
import sys
from pathlib import Path

# Allow running as a plain script (python3 memlab/mcp_server.py)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memlab import db                                            # noqa: E402
from memlab.memory import CONFIDENCE, STORE_PATH, TYPES, MemoryStore  # noqa: E402

SERVER_INFO = {"name": "memlab", "version": "0.1.0"}
PROTOCOL_VERSION = "2025-06-18"

# MEMLAB_STORE points at a different memory file (used by the tests)
store = MemoryStore(os.environ.get("MEMLAB_STORE", STORE_PATH))


def _str(desc, enum=None):
    s = {"type": "string", "description": desc}
    if enum:
        s["enum"] = list(enum)
    return s


def _schema(required=(), **props):
    return {"type": "object", "properties": props, "required": list(required)}


# name -> (description, input schema, function, read_only)
TOOLS = {
    "memory_index": (
        "Load this FIRST for every task. The always-on memory index: every accepted decision "
        "in full, plus the list of topics with stored knowledge. Decisions listed here always apply.",
        _schema(),
        lambda a: store.index(),
        True,
    ),
    "memory_lookup": (
        "All accepted memories on one topic (definitions, facts, gotchas, preferences). "
        "Use when the index lists a topic relevant to the task.",
        _schema(["topic"], topic=_str("Topic slug from the index, e.g. 'revenue'")),
        lambda a: store.lookup(a["topic"]),
        True,
    ),
    "memory_search": (
        "Accepted memories containing every given word. Use when you're not sure which topic applies.",
        _schema(["text"], text=_str("Words to search for")),
        lambda a: store.search(a["text"]),
        True,
    ),
    "memory_propose": (
        "Propose a new memory for review. One sentence, reusable beyond this task: a business "
        "definition, a decision the user made, a data gotcha, a stable fact. Not task answers. "
        "To change an accepted memory, propose the new version with `supersedes` set to its id.",
        _schema(
            ["type", "topic", "statement", "source", "proposed_by"],
            type=_str("Kind of memory", TYPES),
            topic=_str("Short topic slug, e.g. 'revenue', 'dates', 'playlists'"),
            statement=_str("One sentence, max 280 characters"),
            source=_str("Where this came from, e.g. 'user said so', 'query result'"),
            proposed_by=_str("Your agent name"),
            confidence=_str("How sure you are", CONFIDENCE),
            evidence=_str("Optional proof, e.g. the SQL that shows it"),
            supersedes=_str("Optional id of the accepted memory this replaces"),
        ),
        lambda a: store.propose(a["type"], a["topic"], a["statement"], a["source"], a["proposed_by"],
                                a.get("confidence", "medium"), a.get("evidence"), a.get("supersedes")),
        False,
    ),
    "memory_pending": (
        "Memory manager only: proposals waiting for review, with full detail.",
        _schema(),
        lambda a: store.pending(),
        True,
    ),
    "memory_review": (
        "Memory manager only: accept or reject a proposal. Rejections need a note explaining why.",
        _schema(
            ["id", "decision", "reviewed_by"],
            id=_str("Proposal id, e.g. M007"),
            decision=_str("Outcome", ("accept", "reject")),
            reviewed_by=_str("Your agent name"),
            note=_str("Reason (required when rejecting)"),
        ),
        lambda a: (store.accept(a["id"], a["reviewed_by"], a.get("note")) if a["decision"] == "accept"
                   else store.reject(a["id"], a["reviewed_by"], a.get("note"))),
        False,
    ),
    "memory_verify": (
        "Memory manager only: record that an accepted memory was re-checked and still holds.",
        _schema(["id"], id=_str("Memory id")),
        lambda a: store.verify(a["id"]),
        False,
    ),
    "db_schema": (
        "Compact schema of the Chinook music-store database: tables, columns, row counts.",
        _schema(),
        lambda a: db.schema(),
        True,
    ),
    "db_query": (
        f"Run one read-only SQLite query on the Chinook database. Returns at most {db.MAX_ROWS} rows.",
        _schema(["sql"], sql=_str("A single SELECT statement")),
        lambda a: db.query(a["sql"]),
        True,
    ),
}


def tool_list():
    return [
        {
            "name": name,
            "description": desc,
            "inputSchema": schema,
            "annotations": {"readOnlyHint": read_only},
        }
        for name, (desc, schema, _, read_only) in TOOLS.items()
    ]


def call_tool(name, args):
    if name not in TOOLS:
        return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}], "isError": True}
    try:
        result = TOOLS[name][2](args or {})
        text = result if isinstance(result, str) else json.dumps(result, indent=1)
        return {"content": [{"type": "text", "text": text}], "isError": False}
    except Exception as e:  # tool errors go back to the AI as text it can act on
        return {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}


def handle(msg):
    """Return the reply for one incoming message, or None for notifications."""
    method, msg_id = msg.get("method"), msg.get("id")
    if msg_id is None:                      # notifications (e.g. initialized) get no reply
        return None
    if method == "initialize":
        version = msg.get("params", {}).get("protocolVersion", PROTOCOL_VERSION)
        result = {"protocolVersion": version, "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO}
    elif method == "tools/list":
        result = {"tools": tool_list()}
    elif method == "tools/call":
        params = msg.get("params", {})
        result = call_tool(params.get("name"), params.get("arguments"))
    elif method == "ping":
        result = {}
    else:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def main():
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            reply = handle(json.loads(line))
        except json.JSONDecodeError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
