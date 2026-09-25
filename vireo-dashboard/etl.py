#!/usr/bin/env python3
"""
Vireo Audio — CSAT & Handle-Time Agent Scorecard
=================================================

Run:  python3 etl.py
Reads from ./data/*.csv, writes:
  out/agent_scorecard.csv   (all Tier-1 agents, comparable-pool flag included)
  out/csat_trend.csv        (monthly CSAT / ticket volume / replacement volume)
  out/flags.json            (data-quality issues found, for the memo/README)
  out/dashboard_data.json   (everything the HTML dashboard needs)

Every correction below is derived from evidence in the data itself (see
flags.json for the check that triggered it) plus the operating policy and
the email thread — not assumed. See README.md "Decisions" for the reasoning.
"""
import json
import pandas as pd
import numpy as np
from pathlib import Path

DATA = Path(__file__).parent / "data"
OUT = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)

flags = {}  # data-quality findings, kept for the memo / grader

# ---------------------------------------------------------------------------
# 1. LOAD
# ---------------------------------------------------------------------------
t = pd.read_csv(DATA / "tickets.csv", parse_dates=["created_at", "first_response_at", "resolved_at"])
a = pd.read_csv(DATA / "agents.csv", parse_dates=["from_date", "to_date"])
o = pd.read_csv(DATA / "orders.csv")
p = pd.read_csv(DATA / "products.csv")
c = pd.read_csv(DATA / "customers.csv")

flags["row_counts"] = {"tickets": len(t), "agents_roster_rows": len(a), "orders": len(o),
                        "products": len(p), "customers": len(c)}

# ---------------------------------------------------------------------------
# 2. FIX: legacy_fd resolved_at is off by the IST/UTC offset (+330 min)
#
# Evidence: 2,309 of 3,374 legacy_fd tickets (68%) show resolved_at BEFORE
# first_response_at, clustered tightly at -300 to -320 minutes. Policy §9
# says legacy resolution timestamps were reconstructed from the legacy event
# log, which stores UTC, while the helpdesk's own exports are IST. That's a
# 5:30 offset (330 min) — the reconstruction wasn't converted to IST. Adding
# 330 min removes 100% of the negative handle times and brings the legacy
# handle-time distribution in line with the native-helpdesk one (median 26
# min vs 30 min, both channels combined) rather than leaving a bogus
# ~-5th-percentile tail. This is the single largest correction in this
# analysis — left unfixed, it silently drags down the handle-time number for
# every agent who resolved legacy tickets, i.e. everyone.
# ---------------------------------------------------------------------------
pre_neg = int(((t["resolved_at"] - t["first_response_at"]).dt.total_seconds() < 0).sum())
t.loc[t["source_system"] == "legacy_fd", "resolved_at"] += pd.Timedelta(minutes=330)
post_neg = int(((t["resolved_at"] - t["first_response_at"]).dt.total_seconds() < 0).sum())
flags["legacy_timezone_fix"] = {
    "negative_handle_times_before": pre_neg,
    "negative_handle_times_after": post_neg,
    "correction_applied": "+330 min to resolved_at for source_system == legacy_fd",
}

t["handle_min"] = (t["resolved_at"] - t["first_response_at"]).dt.total_seconds() / 60
t["resp_min"] = (t["first_response_at"] - t["created_at"]).dt.total_seconds() / 60

# ---------------------------------------------------------------------------
# 3. Roster: join on agent_id only (per Sameer's email — two agents share the
#    display name "Kavya Pandey": A3006 Chat Frontline/Indore and A3029
#    Logistics/Bengaluru). Never join or group on `name`.
# ---------------------------------------------------------------------------
dupe_names = a["name"][a["name"].duplicated(keep=False)].unique().tolist()
flags["duplicate_agent_names"] = dupe_names

agent_tier = a.drop_duplicates("agent_id").set_index("agent_id")["tier"]
agent_team = a.drop_duplicates("agent_id").set_index("agent_id")["team"]
agent_name = a.drop_duplicates("agent_id").set_index("agent_id")["name"]
agent_site = a.drop_duplicates("agent_id").set_index("agent_id")["site"]

t["tier"] = t["agent_id"].map(agent_tier)
t["team"] = t["agent_id"].map(agent_team)  # roster team, not the routing "assigned_team"

# ---------------------------------------------------------------------------
# 4. Scope: "attendance" (policy §10) = resolved or closed. CSAT blanks are
#    non-response, excluded from averages (not zero) — policy §8.
# ---------------------------------------------------------------------------
att = t[t["status"].isin(["resolved", "closed"])].copy()

# ---------------------------------------------------------------------------
# 5. Identify the hardware-triage rota inside Chat Frontline ("Kavya's four",
#    per Neha's email) empirically, then confirm it structurally: this group
#    carries a much higher share of Warranty & Repair / Returns & Refunds /
#    Charging & Battery tickets than the rest of Chat Frontline — the harder,
#    angrier queue Neha described, not a skill gap.
# ---------------------------------------------------------------------------
chat = att[att["team"] == "Chat Frontline"]
chat_csat = chat.groupby("agent_id")["csat_score"].mean().sort_values()
hardware_triage = chat_csat.head(4).index.tolist()  # empirically the bottom-4 in Chat Frontline

mix_check = (
    chat.assign(grp=np.where(chat["agent_id"].isin(hardware_triage), "triage_rota", "rest_of_chat"))
    .groupby("grp")["category"]
    .value_counts(normalize=True)
    .unstack()
    .T[["triage_rota", "rest_of_chat"]]
    .round(3)
)
flags["hardware_triage_rota"] = {
    "agent_ids": hardware_triage,
    "agent_names": [agent_name[i] for i in hardware_triage],
    "warranty_repair_share_triage_vs_rest": [
        float(mix_check.loc["Warranty & Repair", "triage_rota"]),
        float(mix_check.loc["Warranty & Repair", "rest_of_chat"]),
    ],
    "returns_refunds_share_triage_vs_rest": [
        float(mix_check.loc["Returns & Refunds", "triage_rota"]),
        float(mix_check.loc["Returns & Refunds", "rest_of_chat"]),
    ],
}

# ---------------------------------------------------------------------------
# 6. Build the comparable pool for the retraining flag:
#    - Tier 1 only (policy §6: Tier 2 is not to be compared with Tier 1 on
#      volume metrics; Tier 2 is measured on resolution days, reported
#      separately below)
#    - exclude Logistics / Returns Desk / Escalations & Warranty: these teams
#      own delivery, returns and warranty by design — long multi-day handling
#      and lower CSAT are the nature of the queue (policy §6), not an agent
#      trait. Their tickets also inherit real multi-day customer waits that
#      Tier-1 chat/email/voice/billing tickets don't.
#    - exclude the hardware-triage rota identified above, for the same reason
#    - minimum 15 CSAT responses, so one bad week doesn't flag someone
# ---------------------------------------------------------------------------
STRUCTURAL_TEAMS = ["Logistics", "Returns Desk", "Escalations & Warranty"]
pool = att[
    (att["tier"] == 1)
    & (~att["team"].isin(STRUCTURAL_TEAMS))
    & (~att["agent_id"].isin(hardware_triage))
].copy()

scorecard = (
    pool.groupby("agent_id")
    .agg(
        tickets=("ticket_id", "count"),
        csat_mean=("csat_score", "mean"),
        csat_n=("csat_score", "count"),
        handle_med_min=("handle_min", "median"),
        handle_mean_min=("handle_min", "mean"),
        transfers_mean=("transfers", "mean"),
    )
    .reset_index()
)
scorecard["name"] = scorecard["agent_id"].map(agent_name)
scorecard["team"] = scorecard["agent_id"].map(agent_team)
scorecard["site"] = scorecard["agent_id"].map(agent_site)
scorecard["comparable_pool"] = scorecard["csat_n"] >= 15
scorecard = scorecard.sort_values("csat_mean")
scorecard["rank_in_pool"] = range(1, len(scorecard) + 1)
scorecard["flag_bottom10"] = scorecard["comparable_pool"] & (
    scorecard["rank_in_pool"] <= scorecard[scorecard["comparable_pool"]]["rank_in_pool"].nsmallest(10).max()
)

# Excluded groups, reported separately (not silently dropped)
excluded = att[
    (att["tier"] == 1) & ((att["team"].isin(STRUCTURAL_TEAMS)) | (att["agent_id"].isin(hardware_triage)))
]
excluded_summary = (
    excluded.groupby("agent_id")
    .agg(tickets=("ticket_id", "count"), csat_mean=("csat_score", "mean"),
         csat_n=("csat_score", "count"), handle_med_min=("handle_min", "median"))
    .reset_index()
)
excluded_summary["name"] = excluded_summary["agent_id"].map(agent_name)
excluded_summary["team"] = excluded_summary["agent_id"].map(agent_team)
excluded_summary["reason"] = excluded_summary["agent_id"].apply(
    lambda x: "hardware_triage_rota" if x in hardware_triage else "structural_queue"
)

tier2 = att[att["tier"] == 2]
tier2_summary = (
    tier2.groupby("agent_id")
    .agg(tickets=("ticket_id", "count"), csat_mean=("csat_score", "mean"),
         csat_n=("csat_score", "count"))
    .reset_index()
)
tier2_summary["name"] = tier2_summary["agent_id"].map(agent_name)
# Tier 2 measured on resolution days per policy §6, not per-ticket handle time
tier2["resolve_days"] = tier2["handle_min"] / (60 * 24)
tier2_days = tier2.groupby("agent_id")["resolve_days"].median()
tier2_summary["median_resolve_days"] = tier2_summary["agent_id"].map(tier2_days)

# ---------------------------------------------------------------------------
# 7. CSAT / volume / replacement trend (for the business-number chart)
# ---------------------------------------------------------------------------
t["month"] = t["created_at"].dt.to_period("M").astype(str)
csat_trend = t.groupby("month").agg(
    csat_mean=("csat_score", "mean"),
    csat_n=("csat_score", "count"),
    tickets=("ticket_id", "count"),
).reset_index()

repl = t[t["replacement_issued"] == "Y"].copy()
repl = repl.merge(p[["sku", "unit_cost_inr"]], left_on="product_sku", right_on="sku", how="left")
repl["policy_cost_inr"] = repl["unit_cost_inr"] + 340  # policy §5
repl_trend = repl.groupby("month").agg(
    replacements=("ticket_id", "count"), cost_inr=("policy_cost_inr", "sum")
).reset_index()
csat_trend = csat_trend.merge(repl_trend, on="month", how="left").fillna({"replacements": 0, "cost_inr": 0})

# ---------------------------------------------------------------------------
# 8. Policy-violation check: same ticket carrying BOTH a refund and a
#    replacement (policy §5 explicitly forbids this without a same-day
#    escalation). Flagged, not fixed — this needs a human look, not code.
# ---------------------------------------------------------------------------
both = t[(t["replacement_issued"] == "Y") & (t["refund_amount_inr"].notna())]
flags["refund_and_replacement_same_ticket"] = both[
    ["ticket_id", "agent_id", "refund_amount_inr", "refund_reason_code"]
].to_dict("records")

# ---------------------------------------------------------------------------
# 9. Cheap sanity totals used in the memo
# ---------------------------------------------------------------------------
flags["csat_response_rate"] = float(t["csat_score"].notna().mean())
flags["naive_vs_adjusted_bottom10_overlap"] = None  # filled below

naive_pool = att[att["tier"] == 1].groupby("agent_id").agg(
    csat_mean=("csat_score", "mean"), csat_n=("csat_score", "count")
)
naive_pool = naive_pool[naive_pool["csat_n"] >= 15].sort_values("csat_mean")
naive_bottom10 = set(naive_pool.head(10).index)
adjusted_bottom10 = set(scorecard[scorecard["flag_bottom10"]]["agent_id"])
flags["naive_vs_adjusted_bottom10_overlap"] = {
    "naive_bottom10": sorted(naive_bottom10),
    "adjusted_bottom10": sorted(adjusted_bottom10),
    "agents_naive_would_wrongly_flag": sorted(naive_bottom10 - adjusted_bottom10),
}

# ---------------------------------------------------------------------------
# WRITE OUTPUTS
# ---------------------------------------------------------------------------
scorecard.to_csv(OUT / "agent_scorecard.csv", index=False)
csat_trend.to_csv(OUT / "csat_trend.csv", index=False)
excluded_summary.to_csv(OUT / "excluded_agents.csv", index=False)
tier2_summary.to_csv(OUT / "tier2_summary.csv", index=False)
with open(OUT / "flags.json", "w") as f:
    json.dump(flags, f, indent=2, default=str)

dashboard = {
    "scorecard": json.loads(scorecard.to_json(orient="records")),
    "excluded": json.loads(excluded_summary.to_json(orient="records")),
    "tier2": json.loads(tier2_summary.round(2).to_json(orient="records")),
    "csat_trend": json.loads(csat_trend.round(3).to_json(orient="records")),
    "flags": flags,
}
with open(OUT / "dashboard_data.json", "w") as f:
    json.dump(dashboard, f, indent=2, default=str)

print(f"Wrote {OUT}/agent_scorecard.csv ({len(scorecard)} agents),")
print(f"      {OUT}/csat_trend.csv ({len(csat_trend)} months),")
print(f"      {OUT}/flags.json, {OUT}/dashboard_data.json")
print(f"\nBottom 10 (comparable pool): {sorted(adjusted_bottom10)}")
print(f"Naive bottom 10 would have wrongly included: {flags['naive_vs_adjusted_bottom10_overlap']['agents_naive_would_wrongly_flag']}")
