"""The memory store: small, typed, one-sentence memories in one JSON file.

Rules it enforces (see CLAUDE.md for the reasoning):
  - Agents can only *propose*. A reviewer (the memory manager) accepts or
    rejects. Only accepted memories are ever shown to agents.
  - A memory can supersede an older one. When accepted, the old one is
    marked superseded and linked, so agents only see the current answer.
  - Exact duplicates are refused; near-duplicates are flagged for review.
  - The index (tier 1) is tiny and loaded every time: all accepted
    decisions in full, plus a list of topics. Everything else (tier 2) is
    fetched with lookup(topic) or search(text) when needed.
"""

import difflib
import json
import re
from datetime import date
from pathlib import Path

STORE_PATH = Path(__file__).resolve().parent.parent / "memory" / "memories.json"

TYPES = ("decision", "definition", "fact", "gotcha", "preference")
CONFIDENCE = ("high", "medium", "low")
MAX_STATEMENT = 280          # one sentence, not an essay
SIMILAR = 0.8                # difflib ratio that counts as "possibly the same"
INDEX_BUDGET_TOKENS = 800    # warn when the always-loaded index grows past this


class MemoryStoreError(ValueError):
    """A request the store refuses (bad input or an invalid state change)."""


def _normalize(text):
    return re.sub(r"\s+", " ", text.strip().lower()).rstrip(".!")


def _slug(topic):
    slug = re.sub(r"[^a-z0-9]+", "-", topic.strip().lower()).strip("-")
    if not slug:
        raise MemoryStoreError("topic is empty")
    return slug


class MemoryStore:
    def __init__(self, path=STORE_PATH, today=None):
        self.path = Path(path)
        self._today = today or (lambda: date.today().isoformat())

    # ---------- File ----------

    # Every public method re-reads the file first, so several processes
    # (CLI, MCP server, tests) always see the latest memories.
    def _load(self):
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text())["memories"]

    def _save(self, memories):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"memories": memories}, indent=2) + "\n")
        tmp.replace(self.path)    # atomic: never leaves a half-written file

    @staticmethod
    def _find(memories, mem_id):
        for m in memories:
            if m["id"] == mem_id:
                return m
        raise MemoryStoreError(f"no memory with id {mem_id}")

    # ---------- Writing (proposals and reviews) ----------

    def propose(self, type, topic, statement, source, proposed_by,
                confidence="medium", evidence=None, supersedes=None):
        """Add a proposed memory. Returns {"result", "id", "possible_duplicates"}.

        result is "proposed", or "duplicate" if the exact statement already
        exists (then id is the existing memory and nothing is added).
        """
        if type not in TYPES:
            raise MemoryStoreError(f"type must be one of {', '.join(TYPES)}")
        if confidence not in CONFIDENCE:
            raise MemoryStoreError(f"confidence must be one of {', '.join(CONFIDENCE)}")
        statement = " ".join(statement.split())
        if not statement:
            raise MemoryStoreError("statement is empty")
        if len(statement) > MAX_STATEMENT:
            raise MemoryStoreError(f"statement is {len(statement)} chars; keep it to one sentence (max {MAX_STATEMENT})")
        topic = _slug(topic)

        memories = self._load()
        if supersedes:
            old = self._find(memories, supersedes)
            if old["status"] != "accepted":
                raise MemoryStoreError(f"{supersedes} is {old['status']}; only accepted memories can be superseded")

        live = [m for m in memories if m["status"] in ("accepted", "proposed")]
        norm = _normalize(statement)
        for m in live:
            if _normalize(m["statement"]) == norm:
                return {"result": "duplicate", "id": m["id"], "possible_duplicates": []}
        similar = [m["id"] for m in live
                   if m["topic"] == topic and m["id"] != supersedes
                   and difflib.SequenceMatcher(None, _normalize(m["statement"]), norm).ratio() >= SIMILAR]

        new_id = f"M{max([int(m['id'][1:]) for m in memories], default=0) + 1:03d}"
        memories.append({
            "id": new_id,
            "type": type,
            "topic": topic,
            "statement": statement,
            "source": source,
            "evidence": evidence,
            "confidence": confidence,
            "status": "proposed",
            "supersedes": supersedes,
            "superseded_by": None,
            "proposed_by": proposed_by,
            "reviewed_by": None,
            "review_note": None,
            "created": self._today(),
            "last_verified": None,
        })
        self._save(memories)
        return {"result": "proposed", "id": new_id, "possible_duplicates": similar}

    def accept(self, mem_id, reviewed_by, note=None):
        memories = self._load()
        m = self._find(memories, mem_id)
        if m["status"] != "proposed":
            raise MemoryStoreError(f"{mem_id} is {m['status']}; only proposed memories can be accepted")
        if m["supersedes"]:
            old = self._find(memories, m["supersedes"])
            if old["status"] != "accepted":
                raise MemoryStoreError(
                    f"{mem_id} supersedes {old['id']}, which is now {old['status']}; re-propose against the current memory")
            old["status"] = "superseded"
            old["superseded_by"] = mem_id
        m.update(status="accepted", reviewed_by=reviewed_by, review_note=note, last_verified=self._today())
        self._save(memories)
        return m

    def reject(self, mem_id, reviewed_by, note):
        if not note:
            raise MemoryStoreError("give a reason when rejecting, so the proposer can learn from it")
        memories = self._load()
        m = self._find(memories, mem_id)
        if m["status"] != "proposed":
            raise MemoryStoreError(f"{mem_id} is {m['status']}; only proposed memories can be rejected")
        m.update(status="rejected", reviewed_by=reviewed_by, review_note=note)
        self._save(memories)
        return m

    def verify(self, mem_id):
        """Record that an accepted memory was checked and is still true."""
        memories = self._load()
        m = self._find(memories, mem_id)
        if m["status"] != "accepted":
            raise MemoryStoreError(f"{mem_id} is {m['status']}; only accepted memories can be verified")
        m["last_verified"] = self._today()
        self._save(memories)
        return m

    # ---------- Reading ----------

    def get(self, mem_id):
        return self._find(self._load(), mem_id)

    def pending(self):
        """Proposals waiting for the memory manager."""
        return [m for m in self._load() if m["status"] == "proposed"]

    def lookup(self, topic):
        """Tier 2: every accepted memory on one topic."""
        topic = _slug(topic)
        return [m for m in self._load() if m["status"] == "accepted" and m["topic"] == topic]

    def search(self, text):
        """Tier 2: accepted memories containing every word of `text`."""
        words = _normalize(text).split()
        hits = []
        for m in self._load():
            if m["status"] != "accepted":
                continue
            hay = _normalize(f"{m['topic']} {m['statement']}")
            if all(w in hay for w in words):
                hits.append(m)
        return hits

    def index(self, budget_tokens=INDEX_BUDGET_TOKENS):
        """Tier 1: the small text block an agent loads at the start of every task."""
        memories = self._load()
        accepted = [m for m in memories if m["status"] == "accepted"]
        decisions = [m for m in accepted if m["type"] == "decision"]

        topics = {}
        for m in accepted:
            topics.setdefault(m["topic"], {}).setdefault(m["type"], 0)
            topics[m["topic"]][m["type"]] += 1

        lines = [f"# Memory index ({len(accepted)} accepted memories)", "", "## Decisions (always apply)"]
        lines += [f"- [{m['id']}] ({m['topic']}) {m['statement']}" for m in decisions] or ["- none yet"]
        lines += ["", "## Topics (use lookup(topic) for details)"]
        for topic in sorted(topics):
            counts = topics[topic]
            detail = ", ".join(f"{n} {t}" for t, n in sorted(counts.items()))
            lines.append(f"- {topic}: {detail}")
        if not topics:
            lines.append("- none yet")

        waiting = sum(1 for m in memories if m["status"] == "proposed")
        if waiting:
            lines += ["", f"({waiting} proposal(s) waiting for review)"]

        text = "\n".join(lines)
        estimate = len(text) // 4    # rough: ~4 characters per token
        if estimate > budget_tokens:
            text += (f"\n\nWARNING: index is ~{estimate} tokens, over the {budget_tokens} budget. "
                     "Consolidate or supersede decisions.")
        return text
