# Vireo Audio — Agent CSAT & Handle-Time Scorecard

A tool to answer Priya Raman's request: CSAT and handle time per agent, bottom 10
flagged for the Q3 training budget — done in a way that doesn't hand the budget to
the wrong people.

## Run it (clean machine)

```
pip install pandas
python3 etl.py
```

That's the whole pipeline. It reads `data/*.csv`, writes:

- `out/agent_scorecard.csv` — every comparable Tier-1 agent, ranked, bottom-10 flagged
- `out/excluded_agents.csv` — hardware-triage rota + structural-queue agents, reported not dropped
- `out/tier2_summary.csv` — Tier 2 (Escalations & Warranty), measured in resolve-days
- `out/csat_trend.csv` — monthly CSAT and replacement cost
- `out/flags.json` — every data-quality issue this pipeline found, with the evidence
- `out/dashboard_data.json` — the same data, shaped for the dashboard

`dashboard.html` is a static page with that JSON embedded — open it directly in a
browser, no server needed. It's also published at the link in the submission form.

No paid API calls anywhere in this pipeline — see "On AI use" below.

## Decisions (what I chose, and why)

**1. Corrected a timestamp bug in the legacy data before computing anything.**
2,309 of 3,374 `legacy_fd` tickets (68%) had a `resolved_at` earlier than their
`first_response_at`, clustered almost exactly at −5h30m. The policy doc (§9) says
legacy resolution times were reconstructed from an event log stored in UTC, while
the helpdesk's own exports are IST — that's the 5:30 gap, unconverted. I added 330
minutes to `resolved_at` for every `legacy_fd` row. This isn't a guess: after the
fix, the minimum handle time became 5 minutes (matching the native-helpdesk
minimum exactly) and the negative-time count went to zero. Left unfixed, this
would have quietly deflated the handle-time number for every agent who touched a
legacy ticket — i.e., everyone with any tenure.

**2. Joined the roster on `agent_id`, never `name`.** Sameer's email flagged this
directly: "Kavya Pandey" is two different people (A3006, Chat Frontline, Indore;
A3029, Logistics, Bengaluru) with very different jobs and very different numbers.
Grouping by name would have merged them into one nonsensical row.

**3. Built a "comparable pool" instead of ranking everyone together.**
The brief (and the email thread) both hinted this mattered — Neha's email named a
"hardware triage rota" without saying who was in it. I found it empirically (the
bottom 4 CSAT scores inside Chat Frontline), then checked it structurally: that
group carries a hugely disproportionate share of Warranty & Repair and Returns &
Refunds tickets. Combined with Logistics / Returns Desk / Escalations & Warranty
(whose tickets are long and hard by design, per policy §6), 14 of 44 agents are
excluded from the retraining ranking and reported separately instead. Tier 2 is
kept fully out of the Tier-1 comparison and measured on resolve-days, per policy
§6's explicit instruction.

Running the *naive* version (every Tier-1 agent, one ranking, no exclusions) for
comparison: **all 10** of its bottom-10 are agents this analysis excludes for
structural reasons. Zero overlap with the corrected list. That's not a subtle
difference — a naive dashboard would have sent the entire training budget to the
wrong ten people.

**4. CSAT excludes non-responses, not zero-fills them** (policy §8). Response
rate came out to 44.2%, matching the ~45% the policy doc states — used as a
sanity check that ticket selection wasn't biased.

**5. Didn't try to fix the refund+replacement double-dip (6 tickets).**
Policy §5 says this needs a same-day human escalation when it happens. Flagging
it and moving on was the right stopping point for a 5-hour job — guessing at
which one was the "real" one and silently correcting it would have been worse
than leaving it for a person to look at.

**6. Left the ~40 IVR-transcription-garbled voice tickets alone rather than
excluding them.** They're a small share of 11,750 tickets and dropping them
would bias the "which channel breaches SLA most" number for no real gain in this
window. Noted, not acted on.

## What I deliberately left out (scope)

- **No per-ticket LLM classification.** Arjun's email was explicit: no paid model
  calls at ~Rs 5/ticket across ~12,000 tickets. The categorization this tool
  needed (structural queue vs. comparable pool) turned out to be answerable from
  `assigned_team`/`team` plus one category-mix check — no model call needed. If
  Vireo later wants free-text root-causing on the corrected bottom 10's negative
  tickets (maybe 100-200 tickets, not 12,000), that's a cheap, bounded follow-up,
  not part of this deliverable.
- **No agent-level trend-over-time view** (is agent X improving or not). Useful,
  but a five-hour job has to stop somewhere, and the client's ask was framed as
  "who to retrain now," not "who's trending down."
- **No repeat-contact / first-contact-resolution metric**, despite policy §10
  defining it precisely. It requires reliably matching a customer's repeat
  contact to their original ticket, which needs more validation time than this
  window allows to get right — a wrong FCR number is worse than no FCR number.
- **Didn't reconcile orders.csv/lot_code data at all** — Sameer's email said
  explicitly to ignore it if not useful, and nothing in this ask needed it.

## Known issues with this handoff

- The comparable-pool threshold (≥15 CSAT responses, exclude 3 named teams +
  4 named agents) is a reasonable cut given what's in this data pack, not a
  validated statistical threshold — a longer engagement would want confidence
  intervals per agent, not just a raw mean.
- "Billing" agents make up 3 of the corrected bottom 10. That could be individual
  underperformance, or it could be a queue-level issue too (payment-gateway
  failures are inherently frustrating) that this analysis didn't have time to
  rule out — one Billing agent (Thomas Reddy) ranks well above the other three,
  which argues for individual variation, but it's worth Priya's team sanity-
  checking before anyone's bonus or training assignment is finalized on this
  alone.
- Handle-time correction assumes the +330min offset is uniform across all
  `legacy_fd` rows. It fit the negative cluster essentially perfectly, but I
  didn't get to check whether a handful of legacy rows might have been entered
  natively in IST and don't need the shift.

## On AI use

I (an AI assistant, Claude) did the actual data forensics, wrote all the code,
and drafted the memo — that's the AI-assistance in this submission. I did not
wire in a live LLM API call inside the pipeline itself: everything the tool needs
(the timezone bug, the triage-rota detection, the pool exclusions) turned out to
be answerable deterministically from the data plus the policy doc, and Arjun's
email explicitly asked to keep run cost near zero. See the submission form for
more detail on tool/cost/what-was-discarded.
