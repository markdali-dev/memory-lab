# Memory Lab

A small learning project: a lean, reusable **memory layer** for AI agents, tested with a data-analyst agent over a free sample database. It mirrors (in miniature) Mark's work system: Copilot Studio + Power Automate agents over Snowflake, with a curator, intelligence, memory manager and analyst agent, and a feedback loop from analyst to memory.

Goal is learning Claude Code's tools (subagents, skills, MCP, CLAUDE.md, tests), not a production product. Keep it small, cheap and readable. A few hours a week.

## Principles
- Lean memory: small typed one-sentence records, not transcripts or big files.
- Decisions are always remembered: accepted decisions are in the always-loaded index, every time.
- Two tiers: a tiny index loaded every time; everything else looked up by topic on demand.
- Supersede, don't pile up: a changed decision replaces the old one (old kept, marked superseded, linked).
- Agents propose, one curator decides: only the memory manager accepts/rejects/supersedes.
- Measure value: run the analyst with memory off vs on over a fixed question set.
- No cost: free public data, Python standard library only, agents run as Claude Code subagents (no API key).

## Data
- `data/chinook.sqlite`: Chinook sample database (fictional digital music store, 2009 to 2013), MIT license in `data/CHINOOK_LICENSE.md`. Tables: Artist, Album, Track, Genre, MediaType, Playlist, PlaylistTrack, Customer, Employee, Invoice, InvoiceLine.
- Always opened read-only.

## Memory record
One JSON file, `memory/memories.json` (diffs in git show what memory learned). Each record:
- `id` (M001...), `type` (decision | definition | fact | gotcha | preference), `topic` (lowercase slug), `statement` (one sentence, max 280 chars)
- `source` (who/what produced it), `evidence` (optional, e.g. the SQL that proves it), `confidence` (high | medium | low)
- `status` (proposed | accepted | rejected | superseded), `supersedes` / `superseded_by`, `proposed_by`, `reviewed_by`, `review_note`
- `created`, `last_verified` (dates)

## Code layout
- `memlab/db.py`: read-only SQL against Chinook, row cap, schema summary.
- `memlab/memory.py`: the memory store (propose, accept, reject, verify, index, lookup, search).
- `memlab/cli.py`: command line to inspect and drive memory by hand: `python3 -m memlab.cli --help`.
- `memlab/mcp_server.py`: MCP server over stdio, hand-written JSON-RPC (no SDK). Registered in `.mcp.json` as `memlab`, pre-approved in `.claude/settings.json`. Tools: memory_index, memory_lookup, memory_search, memory_propose (any agent); memory_pending, memory_review, memory_verify (memory manager only, enforced by each agent's tool list); db_schema, db_query. `MEMLAB_STORE` env var swaps the memory file (tests).
- `.claude/agents/`: `profiler.md`, `analyst.md`, `memory-manager.md`. Each lists its allowed memlab tools; that list is what enforces who may do what.
- `scripts/run_agent.py`: run one agent headless with its answer and cost (turns, tokens, time): `python3 scripts/run_agent.py analyst "question"`.
- `tests/`: `python3 -m unittest -v`.

## Feedback loop contract
- Who can write: profiler and analyst can only `memory_propose`. Only memory-manager can `memory_review` (accept/reject) and `memory_verify`. Mark's own decisions are proposed via the CLI (`--by mark`) and reviewed the same way.
- Analyst: `memory_index` first and follow every decision; `memory_lookup` only relevant topics; query the DB; answer ending with `Memory used: <ids>`; then propose at most 3 reusable learnings (search first, never the answer itself, never invented decisions).
- What gets proposed: decision (only when the user stated it; source quotes them), gotcha/fact (with evidence SQL), definition (term to tables/joins).
- Manager accepts only if: one standalone sentence, reusable, right type (decisions must come from a person), evidence re-run and holds, not a duplicate, no unflagged conflict (changes must use `supersedes`), existing topic reused where it fits. Rejections carry a reason.

## Build order
1. Database + memory store (done when tests pass).
2. MCP server exposing memory + database tools.
3. Agents as Claude Code subagents: profiler seeds memory; analyst answers and proposes; memory-manager reviews. Feedback loop contract.
4. Evaluation: ~15 questions, memory off vs on: correctness, tool calls, tokens.

## Known traps in the data (material for step 3)
Most of these can't be worked out from the schema alone, which is exactly where memory should help:
- Data runs 2009-01-01 to 2013-12-22, so "this year" / "last year" must mean 2013 / 2012, not today's date.
- About 9.5% of sales (220.89 of 2,328.60) are videos (MediaType "Protected MPEG-4 video file": TV shows, movies), so "music revenue" is ambiguous.
- Playlist names are duplicated (Music, Movies, TV Shows, Audiobooks appear twice each), and PlaylistTrack has 8,715 rows for 3,503 tracks, so counting tracks through playlists over-counts.
- "Sales by employee" can only go through Customer.SupportRepId (3 Sales Support Agents); employees aren't on invoices.
- Revenue: Invoice.Total equals the sum of InvoiceLine.UnitPrice × Quantity (2,328.60 both ways); every Quantity is 1.

## Status
- Step 1 done: database + memory store + CLI.
- Step 2 done: MCP server; 18 tests passing (incl. end-to-end over stdio); verified Claude Code calls its tools.
- Step 3 done: three agents + runner. First run: profiler proposed 8 (with SQL proof), Mark's 3 decisions added, manager accepted 10 and rejected 1 (overlapped a decision). Analyst then answered decision-dependent questions correctly in 6 to 7 turns, and a rule Mark stated mid-question went analyst, then proposal, then accepted (M012). Analyst confirmed unable to review.
- Memory: 11 accepted, 4 decisions (M009 music excludes video, M010 2013 = this year, M011 top customers by spend, M012 show all ties).
- Next: step 4 (evaluation, memory off vs on).
- Later idea: an HTTP transport would let claude.ai or Copilot Studio use the same server (stdio only works for local apps like Claude Code).
