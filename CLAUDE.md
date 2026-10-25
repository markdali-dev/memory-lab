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
- `tests/`: `python3 -m unittest -v`.

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
- Step 1 done: database + memory store + CLI, 14 tests passing. Memory is empty.
