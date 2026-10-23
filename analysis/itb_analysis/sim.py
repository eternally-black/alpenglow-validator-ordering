"""Scheduler simulator (PLAN §4.4): synthetic campaign data with *known* ordering rules, written in the exact raw
format of docs/DATA.md, so the real analysis pipeline — including its strict eligibility checks — runs unchanged.

It answers "does the experiment measure what it claims?" before any live data: for each declared scenario we
measure how often the pre-registered procedure returns the right verdict, a wrong one, or "none/unidentified".
It models observable consequences, not any validator's implementation, and deliberately includes look-alikes
built to fool the analysis (pacing, label-blind reordering, selective dropping, assignment-dependent pair loss,
mode switches, key + FIFO tie-breaks).

Times are milliseconds relative to the leader's window start (leader frame). The window is finite: four slots of
≈130 ms (the observed post-Alpenglow in-window cadence); anything scheduled after it spills to the next leader
(shared ingress) or expires (direct ingress — unstaked transactions are not forwarded).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

SLOT_MS = 130.0
WINDOW_SLOTS = 4
WINDOW_MS = SLOT_MS * WINDOW_SLOTS
HOLD_SLOTS = 20
REAL_SLOT_MS = 235.0
PRIORITY_MULTIPLIER = 1_000_000
AGAVE_LIKE = {"Agave", "JitoLabs", "Rakurai", "AgaveBam", "HarmonicAgave"}
SHARED = {"bam_node", "harmonic_remote_tpu"}


# ---------------------------------------------------------------- probe arithmetic (crates/itb/src/probe.rs)
def priority_fee(t: dict) -> int:
    return math.ceil(t["cu_limit"] * t["cu_price_micro_lamports"] / 1_000_000)


def cost(t: dict) -> int:
    return 720 + 2 * 300 + 31 // 4 + t["cu_limit"] + 8 * math.ceil(t["loaded_data_limit"] / 32768)


def agave_priority(t: dict) -> int:
    return (2500 + priority_fee(t)) * PRIORITY_MULTIPLIER // (cost(t) + 1)


KEYS = {
    "cu_price": lambda t: t["cu_price_micro_lamports"],
    "lamport_fee": priority_fee,
    "reward_cost": agave_priority,
}


@dataclass
class Params:
    scenario: str
    seed: int = 0
    landing: float = 0.9
    #: independent per-stream path noise; back-to-back streams are 0.05 ms apart on one connection
    jitter_ms: float = 0.02
    latency_ms: float = 30.0
    t_ms: float = 50.0
    pass_ms: float = 1.0
    pace_ms: float = 20.0
    drop_q: float = 0.5
    reverse_q: float = 0.35
    loss_q: float = 0.8
    base: str = "cu_price_batch"
    mode_b: str = "fifo"
    spill_p: float = 0.7
    #: observation failures, per window: one stream fails, the leader produces no block, gossip changes mid-window
    p_transport_error: float = 0.02
    p_unproduced: float = 0.02
    p_transition: float = 0.03
    #: targets that follow `control_scenario` whatever the scenario (the positive controls: known reward/cost)
    controls: tuple = ()
    control_scenario: str = "reward_cost_greedy"
    extra: dict = field(default_factory=dict)


@dataclass
class Item:
    probe: dict
    arrival: float
    key: dict
    lock: int
    sched: float = 0.0
    rank: float = 0.0
    landed: bool = True
    spill: bool = False


# ---------------------------------------------------------------- ordering rules
def _greedy(items, p, rng, key="reward_cost"):
    """Streaming priority scheduler: a pass every pass_ms (random phase); available items scheduled in key order.
    Items sharing a lock keep key order; independent items land in random worker order."""
    pending = sorted(items, key=lambda i: i.arrival)
    phase = rng.uniform(0, p.pass_ms)
    t, order = phase, 0
    counts = {}
    for i in items:
        counts[i.lock] = counts.get(i.lock, 0) + 1
    while pending:
        avail = [i for i in pending if max(i.arrival, 0.0) <= t]
        if not avail:
            nxt = max(pending[0].arrival, 0.0)
            t = max(t + p.pass_ms, phase + math.ceil((nxt - phase) / p.pass_ms) * p.pass_ms)
            continue
        avail.sort(key=lambda i: (-i.key[key], rng.random()))
        for i in avail:
            i.sched = t
            i.rank = order + (rng.random() * len(avail) if counts[i.lock] == 1 else 0.0)
            order += 1
            pending.remove(i)
        t += p.pass_ms


def _paced(items, p, rng):
    """Pending queue drained one item per pace_ms opportunity, best reward/cost first (pacing look-alike)."""
    pending = list(items)
    t, order = rng.uniform(0, p.pace_ms), 0
    while pending:
        avail = [i for i in pending if max(i.arrival, 0.0) <= t]
        if avail:
            best = max(avail, key=lambda i: (i.key["reward_cost"], rng.random()))
            best.sched, best.rank = t, order
            order += 1
            pending.remove(best)
        t += p.pace_ms


def _batch(items, p, rng, key, shared, fifo_ties=False):
    """Auction every t_ms with a random phase; each batch sorted by `key` (ties random, or by arrival with
    fifo_ties); batches in time order. Batches closed before the window go to the previous leader on shared ingress,
    or are held for slot start on direct ingress."""
    phase = rng.uniform(0, p.t_ms)
    for i in items:
        b = math.floor((i.arrival - phase) / p.t_ms)
        end = phase + (b + 1) * p.t_ms
        if end < 0:
            if shared:
                i.spill = True
            end = 0.0
        i.sched = end
        tie = i.arrival * 1e-6 if fifo_ties else rng.random() * 1e-3
        i.rank = end * 1e9 - i.key[key] + tie


def _fifo(items, p, rng, extra_jitter=0.0):
    for i in items:
        a = i.arrival + (rng.normal(0, extra_jitter) if extra_jitter else 0.0)
        i.sched = max(a, 0.0)
        i.rank = a


def _random(items, p, rng):
    for i in items:
        i.sched = max(i.arrival, 0.0)
        i.rank = rng.random()


def _pairs(items):
    by_pair = {}
    for i in items:
        by_pair.setdefault(i.probe["pair_id"], []).append(i)
    return [m for m in by_pair.values() if len(m) == 2]


def apply_rule(name, items, p, rng, shared):
    if name == "reward_cost_greedy":
        _greedy(items, p, rng)
    elif name == "streaming_pacing":
        _paced(items, p, rng)
    elif name == "cu_price_fifo_tie":
        _batch(items, p, rng, "cu_price", shared, fifo_ties=True)
    elif name.endswith("_batch"):
        _batch(items, p, rng, name.removesuffix("_batch"), shared)
    elif name == "fifo":
        _fifo(items, p, rng)
    elif name == "fifo_reorder":
        _fifo(items, p, rng, extra_jitter=2.0)
    elif name == "label_blind_reorder":
        # FIFO, but each pair's order is reversed with probability reverse_q regardless of labels.
        _fifo(items, p, rng)
        for a, b in _pairs(items):
            if rng.random() < p.reverse_q:
                a.rank, b.rank = b.rank, a.rank
    elif name == "random":
        _random(items, p, rng)
    elif name == "selective_drop":
        apply_rule(p.base, items, p, rng, shared)
        base_key = "reward_cost" if p.base in ("reward_cost_greedy", "streaming_pacing") else p.base.removesuffix("_batch")
        for members in _pairs(items):
            if base_key in KEYS:
                lo = min(members, key=lambda i: i.key[base_key])
                if lo.key[base_key] < max(i.key[base_key] for i in members) and rng.random() < p.drop_q:
                    lo.landed = False
    elif name == "correlated_pair_loss":
        # FIFO ordering, but whole pairs are lost when the table's first label (x) was sent second, with
        # probability loss_q: complete pairs then over-represent "x sent first" (assignment-dependent selection).
        _fifo(items, p, rng)
        for a, b in _pairs(items):
            x = a if a.probe["label"] == a.probe["pair_x_label"] else b
            if x.probe["send_position_in_pair"] == 1 and rng.random() < p.loss_q:
                a.landed = b.landed = False
    elif name == "balanced_double_loss":
        # The gate-1b counterexample (R2): a label-blind order — the winning *send position* is drawn once per window —
        # and both members of a C1/C2 pair are lost whenever that order would make y win. The retained pairs stay
        # balanced in send order and x wins all of them; only the pairs lost entirely reveal the selection.
        _fifo(items, p, rng)
        win_first = rng.random() < 0.5
        for a, b in _pairs(items):
            if not win_first:
                a.rank, b.rank = b.rank, a.rank
            first = a if a.probe["send_position_in_pair"] == 0 else b
            winner = first if win_first else (b if first is a else a)
            if a.probe["pair_kind"] in ("c1", "c2") and winner.probe["label"] != winner.probe["pair_x_label"]:
                a.landed = b.landed = False
    elif name == "mode_switch":
        apply_rule(p.base if rng.random() < 0.5 else p.mode_b, items, p, rng, shared)
    else:
        raise ValueError(f"unknown scenario {name}")


X_LABEL = {"c1": "A", "c2": "A'", "c3": "A", "c2_uncontended": "A'", "race": "hi", "equal_key": "A"}


# ---------------------------------------------------------------- one window
def _sig(*parts) -> str:
    return hashlib.sha256("/".join(map(str, parts)).encode()).hexdigest()[:64]


def simulate_window(plan, target, p, rng, run_id, start_ns):
    probes, items = [], []
    for pair in plan["pairs"]:
        for pos, m in enumerate(pair["members"]):
            t = m["template"]
            nominal = plan["burst_offset_ms"] + m["send_offset_ms"]
            probe = {
                "run_id": run_id,
                "probe_id": f"{pair['pair_id']}/{m['label']}",
                "target_identity": plan["target_identity"],
                "seq": plan["seq"],
                "stage": plan["stage"],
                "tier": plan.get("tier", "core"),
                "kit": plan["kit"],
                "regime": plan["regime"],
                "pair_id": pair["pair_id"],
                "pair_kind": pair["kind"],
                "label": m["label"],
                "send_position_in_pair": pos,
                "race_dt_ms": pair.get("race_dt_ms"),
                "template": t,
                "priority_fee": priority_fee(t),
                "total_fee": 5000 + priority_fee(t),
                "cost": cost(t),
                "agave_priority": agave_priority(t),
                "lock_index": m["lock_index"],
                "signature": _sig(run_id, plan["target_identity"], plan["seq"], pair["pair_id"], m["label"]),
                "window_first_slot": plan["window_first_slot"],
                "window_last_slot": plan["window_first_slot"] + 3,
                "anchor": "window_slot" if nominal >= 0 else ("prev_slot" if nominal >= -250 else "estimate"),
                "nominal_offset_ms": nominal,
            }
            probes.append(probe)
            arrival = nominal + p.latency_ms + pos * 0.05 + rng.normal(0, p.jitter_ms)
            items.append(Item(dict(probe, pair_x_label=X_LABEL.get(pair["kind"], "A")), arrival, {k: f(t) for k, f in KEYS.items()}, m["lock_index"]))

    shared = target["ingress"] in SHARED
    if plan["kit"] in ("h", "s"):
        for i in items:
            send = i.probe["nominal_offset_ms"]
            if plan["kit"] == "h":
                i.landed = target["client_id"] not in AGAVE_LIKE or send >= -HOLD_SLOTS * REAL_SLOT_MS
            else:
                i.spill = rng.random() < p.spill_p
            i.sched, i.rank = 0.0, rng.random()
    else:
        apply_rule(p.scenario, items, p, rng, shared)

    # Observation failures (they exercise eligibility and the stopping predicate exactly as on mainnet).
    unproduced = rng.random() < p.p_unproduced
    failed_stream = int(rng.integers(len(items))) if items and rng.random() < p.p_transport_error else None
    transition = rng.random() < p.p_transition
    if unproduced:
        for i in items:
            i.landed = False
    if failed_stream is not None:
        items[failed_stream].landed = False

    first = plan["window_first_slot"]
    outcomes, placed = [], []
    for i in items:
        o = {"probe_id": i.probe["probe_id"], "signature": i.probe["signature"], "fee": None, "err": None, "cost_units": None,
             "compute_units_consumed": None, "transport_error": None, "slot": None, "index_in_block": None,
             "block_tx_count": None, "leader": None}
        late = i.sched >= WINDOW_MS
        if i.landed and not i.spill and not late and rng.random() < p.landing:
            placed.append((i, first + int(max(i.sched, 0.0) // SLOT_MS)))
            o["status"] = "landed_target"
        elif (i.spill or (late and shared)) and i.landed:
            o.update(status="spillover_other_leader", slot=first - 1 if i.spill else first + WINDOW_SLOTS,
                     index_in_block=int(rng.integers(0, 300)), block_tx_count=300, leader="OTHER_LEADER", fee=i.probe["total_fee"])
        else:
            o["status"] = "expired_confirmed"
        outcomes.append((i, o))
    by_slot = {}
    for i, slot in placed:
        by_slot.setdefault(slot, []).append(i)
    pos_of = {}
    for slot, its in by_slot.items():
        its.sort(key=lambda i: i.rank)
        n_block = int(rng.integers(200, 1500))
        idx = sorted(rng.choice(n_block, size=len(its), replace=False))
        for i, k in zip(its, idx):
            pos_of[id(i)] = (slot, int(k), n_block)
    rows = []
    for i, o in outcomes:
        if o["status"] == "landed_target":
            slot, k, n_block = pos_of[id(i)]
            o.update(slot=slot, index_in_block=k, block_tx_count=n_block, leader=plan["target_identity"],
                     fee=i.probe["total_fee"], cost_units=i.probe["cost"])
        rows.append({"run_id": run_id, "outcome": o})
    sends = []
    for k, i in enumerate(items):
        t = start_ns + int((i.probe["nominal_offset_ms"]) * 1e6)
        err = "write: connection lost" if k == failed_stream else None
        sends.append({"run_id": run_id, "dry_run": False, "record": {
            "probe_id": i.probe["probe_id"], "addr": "sim:1", "scheduled_unix_ns": t, "open_unix_ns": t, "written_unix_ns": t,
            "finished_unix_ns": None if err else t, "stream_index_in_burst": k, "limiter_delay_us": 0,
            "never_opened": False, "error": err}})
    window = {
        "run_id": run_id, "target_identity": plan["target_identity"], "tier": plan.get("tier", "core"),
        "client_id": target["client_id"], "ingress": target["ingress"], "tpu_quic": target.get("tpu_quic", "sim:1"),
        "version": "sim", "seq": plan["seq"], "stage": plan["stage"], "kit": plan["kit"], "regime": plan["regime"],
        "burst_offset_ms": plan["burst_offset_ms"], "window_first_slot": first, "window_last_slot": first + 3,
        "planned_probes": len(items), "sent_ok": len(items) - (failed_stream is not None), "not_sent": 0,
        "transport_errors": int(failed_stream is not None),
        "connect": {"error": None}, "estimated_window_start_unix_ns": start_ns,
        "produced_slots": [] if unproduced else [first + k for k in range(WINDOW_SLOTS)], "live": True,
    }
    return probes, window, rows, sends, transition


# ---------------------------------------------------------------- whole run
def simulate(design_path, targets_path, out_dir, params, stage=1, windows_per_target=None) -> Path:
    rng = np.random.default_rng(params.seed)
    targets = {t["identity"]: t for t in json.loads(Path(targets_path).read_text())}
    plans = [json.loads(l) for l in Path(design_path).read_text().splitlines() if l.strip()]
    if stage is not None:
        plans = [pl for pl in plans if pl["stage"] == stage]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"sim-{params.scenario}-{params.seed}"
    counts, slot, t_ns = {}, 460_100_000, 1_790_000_000 * 10**9
    with (out_dir / "probes.jsonl").open("w") as fp, (out_dir / "windows.jsonl").open("w") as fw, \
            (out_dir / "outcomes.jsonl").open("w") as fo, (out_dir / "target_states.jsonl").open("w") as fs, \
            (out_dir / "sends.jsonl").open("w") as fsend:
        for pl in plans:
            tid = pl["target_identity"]
            if windows_per_target is not None and counts.get(tid, 0) >= windows_per_target:
                continue
            counts[tid] = counts.get(tid, 0) + 1
            gap = int(rng.integers(5, 60))
            slot += 4 * gap
            t_ns += gap * 4 * int(REAL_SLOT_MS * 1e6)
            pl = dict(pl, window_first_slot=slot)
            target = targets[tid]
            tp = replace(params, scenario=params.control_scenario) if tid in params.controls else params
            probes, window, outcomes, sends, transition = simulate_window(pl, target, tp, rng, run_id, t_ns)
            state = {"client_id": target["client_id"], "version": "sim", "tpu_quic": target.get("tpu_quic", "sim:1"),
                     "ingress": target["ingress"], "identity": tid}
            # Bracketing gossip snapshots; a transition changes the advertised TPU in the later one.
            after = dict(state, tpu_quic="sim:2") if transition else state
            for dt, st in ((-10, state), (10, after)):
                fs.write(json.dumps({"at_unix_ns": t_ns + dt * 10**9, "identity": tid, "state": st}) + "\n")
            for x in probes:
                fp.write(json.dumps(x) + "\n")
            fw.write(json.dumps(window) + "\n")
            for x in outcomes:
                fo.write(json.dumps(x) + "\n")
            for x in sends:
                fsend.write(json.dumps(x) + "\n")
    (out_dir / "run_start.json").write_text(json.dumps({
        "run_id": run_id, "mode": "simulated", "stage": stage, "scenario": params.scenario,
        "params": dict(params.__dict__), "design_file": str(design_path),
        "design_sha256": hashlib.sha256(Path(design_path).read_bytes()).hexdigest(),
    }, indent=1))
    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--design", required=True, type=Path)
    ap.add_argument("--targets", required=True, type=Path)
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--t-ms", type=float, default=50.0)
    ap.add_argument("--landing", type=float, default=0.9)
    ap.add_argument("--jitter-ms", type=float, default=0.02)
    ap.add_argument("--stage", type=int, default=1)
    ap.add_argument("--windows-per-target", type=int, default=None)
    a = ap.parse_args()
    simulate(a.design, a.targets, a.out, Params(a.scenario, a.seed, a.landing, a.jitter_ms, t_ms=a.t_ms), a.stage, a.windows_per_target)


if __name__ == "__main__":
    main()
