"""Command line for poking at the memory store and database by hand.

    python3 -m memlab.cli index
    python3 -m memlab.cli propose decision revenue "Revenue means ..." --source "chat" --by mark
    python3 -m memlab.cli pending
    python3 -m memlab.cli accept M001 --by mark
    python3 -m memlab.cli lookup revenue
    python3 -m memlab.cli sql "SELECT COUNT(*) FROM Invoice"
"""

import argparse
import json
import sys

from . import db
from .memory import TYPES, MemoryStore, MemoryStoreError


def show(memories):
    if not memories:
        print("(none)")
    for m in memories:
        extra = f"  supersedes {m['supersedes']}" if m["supersedes"] else ""
        print(f"[{m['id']}] {m['status']:<10} {m['type']:<10} ({m['topic']}) {m['statement']}{extra}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="memlab", description="Memory Lab: memory store and Chinook database")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("index", help="show the always-loaded index (tier 1)")
    sub.add_parser("pending", help="list proposals waiting for review")
    sub.add_parser("all", help="list every memory, any status")
    s = sub.add_parser("lookup", help="accepted memories on a topic"); s.add_argument("topic")
    s = sub.add_parser("search", help="accepted memories containing words"); s.add_argument("text")
    s = sub.add_parser("show", help="full record as JSON"); s.add_argument("id")

    s = sub.add_parser("propose", help="propose a new memory")
    s.add_argument("type", choices=TYPES)
    s.add_argument("topic")
    s.add_argument("statement")
    s.add_argument("--source", required=True)
    s.add_argument("--by", required=True, help="who is proposing")
    s.add_argument("--confidence", default="medium")
    s.add_argument("--evidence")
    s.add_argument("--supersedes")

    for name in ("accept", "reject"):
        s = sub.add_parser(name, help=f"{name} a proposal")
        s.add_argument("id")
        s.add_argument("--by", required=True, help="reviewer")
        s.add_argument("--note", required=(name == "reject"))
    s = sub.add_parser("verify", help="mark an accepted memory as re-checked today"); s.add_argument("id")

    sub.add_parser("schema", help="compact database schema")
    s = sub.add_parser("sql", help="run a read-only query"); s.add_argument("query")

    a = p.parse_args(argv)
    store = MemoryStore()
    try:
        if a.cmd == "index":
            print(store.index())
        elif a.cmd == "pending":
            show(store.pending())
        elif a.cmd == "all":
            show(store._load())
        elif a.cmd == "lookup":
            show(store.lookup(a.topic))
        elif a.cmd == "search":
            show(store.search(a.text))
        elif a.cmd == "show":
            print(json.dumps(store.get(a.id), indent=2))
        elif a.cmd == "propose":
            print(json.dumps(store.propose(a.type, a.topic, a.statement, a.source, a.by,
                                           a.confidence, a.evidence, a.supersedes)))
        elif a.cmd == "accept":
            show([store.accept(a.id, a.by, a.note)])
        elif a.cmd == "reject":
            show([store.reject(a.id, a.by, a.note)])
        elif a.cmd == "verify":
            show([store.verify(a.id)])
        elif a.cmd == "schema":
            print(db.schema())
        elif a.cmd == "sql":
            r = db.query(a.query)
            print(" | ".join(r["columns"]))
            for row in r["rows"]:
                print(" | ".join(str(v) for v in row))
            if r["truncated"]:
                print(f"... (first {db.MAX_ROWS} rows only)")
    except (MemoryStoreError, Exception) as e:  # show a clean one-line error
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
