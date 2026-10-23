"""Scheduler simulator (PLAN §4.4): synthetic campaign data with *known* ordering rules, written in the exact raw
format of docs/DATA.md, so the real analysis pipeline can be run on it unchanged.

It answers "does the experiment measure what it claims?" before any live data: for each declared scenario we measure
how often the pre-registered procedure supports the true rule, supports a wrong one, or reports "no rule".
It is a model of observable consequences, not of any validator's implementation; adversarial look-alikes are
included on purpose (pacing, ingress reordering, selective dropping, mode switches).

Times are in milliseconds relative to the leader's window start (leader frame).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

SLOT_MS = 200.0
HOLD_SLOTS = 20
REAL_SLOT_MS = 235.0
PRIORITY_MULTIPLIER = 1_000_000
AGAVE_LIKE = {"Agave", "JitoLabs", "Rakurai", "AgaveBam", "HarmonicAgave"}


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
    base: str = "cu_price_batch"
    mode_b: str = "fifo"
    spill_p: float = 0.7
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
def _greedy(items: list[Item], p: Params, rng: np.random.Generator, key: str = "reward_cost") -> None:
    """Streaming priority scheduler: a pass every pass_ms; available items scheduled in key order.
    Items with a lock shared in the window keep key order; independent items land in random worker order."""
    pending = sorted(items, key=lambda i: i.arrival)
    # The scheduler's pass grid has no relation to our arrival times: random phase per window.
    phase = rng.uniform(0, p.pass_ms)
    t = phase
    order = 0
    while pending:
        avail = [i for i in pending if max(i.arrival, 0.0) <= t]
        if not avail:
            nxt = max(pending[0].arrival, 0.0)
            t = max(t + p.pass_ms, phase + math.ceil((nxt - phase) / p.pass_ms) * p.pass_ms)
            continue
        avail.sort(key=lambda i: (-i.key[key], rng.random()))
        shared = {i.lock for i in avail}
        counts = {l: sum(1 for i in items if i.lock == l) for l in shared}
        for i in avail:
            i.sched = t
            i.rank = order + (rng.random() * len(avail) if counts[i.lock] == 1 else 0.0)
            order += 1
            pending.remove(i)
        t += p.pass_ms


def _paced(items: list[Item], p: Params, rng: np.random.Generator) -> None:
    """Pending queue drained one item per pace_ms opportunity, best reward/cost first (pacing look-alike)."""
    pending = list(items)
    t = rng.uniform(0, p.pace_ms)
    order = 0
    while pending:
        avail = [i for i in pending if max(i.arrival, 0.0) <= t]
        if avail:
            best = max(avail, key=lambda i: (i.key["reward_cost"], rng.random()))
            best.sched, best.rank = t, order
            order += 1
            pending.remove(best)
        t += p.pace_ms


def _batch(items: list[Item], p: Params, rng: np.random.Generator, key: str, shared_ingress: bool) -> None:
    """Auction every t_ms with a random phase; each batch sorted by `key` (ties random); batches in time order.
    Batches closed before the window start go to the previous leader on shared ingress (spill-over), or are held
    for slot start on direct ingress."""
    phase = rng.uniform(0, p.t_ms)
    for i in items:
        b = math.floor((i.arrival - phase) / p.t_ms)
        end = phase + (b + 1) * p.t_ms
        if end < 0:
            if shared_ingress:
                i.spill = True
            end = 0.0
        i.sched = end
        i.rank = end * 1e9 - i.key[key] + rng.random() * 1e-3


def _fifo(items: list[Item], p: Params, rng: np.random.Generator, extra_jitter: float = 0.0) -> None:
    for i in items:
        a = i.arrival + (rng.normal(0, extra_jitter) if extra_jitter else 0.0)
        i.sched = max(a, 0.0)
        i.rank = a


def _random(items: list[Item], p: Params, rng: np.random.Generator) -> None:
    for i in items:
        i.sched = max(i.arrival, 0.0)
        i.rank = rng.random()


def apply_rule(name: str, items: list[Item], p: Params, rng: np.random.Generator, shared_ingress: bool) -> None:
    if name == "reward_cost_greedy":
        _greedy(items, p, rng)
    elif name == "streaming_pacing":
        _paced(items, p, rng)
    elif name.endswith("_batch"):
        _batch(items, p, rng, name.removesuffix("_batch"), shared_ingress)
    elif name == "fifo":
        _fifo(items, p, rng)
    elif name == "fifo_reorder":
        _fifo(items, p, rng, extra_jitter=2.0)
    elif name == "random":
        _random(items, p, rng)
    elif name == "selective_drop":
        apply_rule(p.base, items, p, rng, shared_ingress)
        base_key = "reward_cost" if p.base in ("reward_cost_greedy", "streaming_pacing") else p.base.removesuffix("_batch")
        by_pair: dict[str, list[Item]] = {}
        for i in items:
            by_pair.setdefault(i.probe["pair_id"], []).append(i)
        for members in by_pair.values():
            if len(members) == 2 and base_key in KEYS:
                lo = min(members, key=lambda i: i.key[base_key])
                if lo.key[base_key] < max(i.key[base_key] for i in members) and rng.random() < p.drop_q:
                    lo.landed = False
    elif name == "mode_switch":
        apply_rule(p.base if rng.random() < 0.5 else p.mode_b, items, p, rng, shared_ingress)
    else:
        raise ValueError(f"unknown scenario {name}")


# ---------------------------------------------------------------- one window
def _sig(*parts) -> str:
    return hashlib.sha256("/".join(map(str, parts)).encode()).hexdigest()[:64]


def simulate_window(plan: dict, target: dict, p: Params, rng: np.random.Generator, run_id: str) -> tuple[list, dict, list]:
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
            # Back-to-back streams on one connection keep their order up to sub-ms jitter.
            arrival = nominal + p.latency_ms + pos * 0.05 + rng.normal(0, p.jitter_ms)
            items.append(Item(probe, arrival, {k: f(t) for k, f in KEYS.items()}, m["lock_index"]))

    shared = target["ingress"] in ("bam_node", "harmonic_remote_tpu")
    if plan["kit"] in ("h", "s"):
        for i in items:
            send = i.probe["nominal_offset_ms"]
            if plan["kit"] == "h":
                held = target["client_id"] not in AGAVE_LIKE or send >= -HOLD_SLOTS * REAL_SLOT_MS
                i.landed, i.sched = held, 0.0
            else:
                i.spill = rng.random() < p.spill_p
                i.sched = 0.0
            i.rank = rng.random()
    else:
        apply_rule(p.scenario, items, p, rng, shared)

    outcomes = []
    landed = [i for i in items if i.landed and not i.spill and rng.random() < p.landing]
    landed_ids = {id(i) for i in landed}
    first = plan["window_first_slot"]
    by_slot: dict[int, list[Item]] = {}
    for i in landed:
        slot = first + min(3, int(max(i.sched, 0.0) // SLOT_MS))
        by_slot.setdefault(slot, []).append(i)
    pos_of: dict[int, tuple[int, int, int]] = {}
    for slot, its in by_slot.items():
        its.sort(key=lambda i: i.rank)
        n_block = int(rng.integers(200, 1500))
        idx = sorted(rng.choice(n_block, size=len(its), replace=False))
        for i, k in zip(its, idx):
            pos_of[id(i)] = (slot, int(k), n_block)
    for i in items:
        o = {"probe_id": i.probe["probe_id"], "signature": i.probe["signature"], "fee": None, "err": None,
             "cost_units": None, "compute_units_consumed": None, "transport_error": None}
        if id(i) in landed_ids:
            slot, k, n_block = pos_of[id(i)]
            o.update(status="landed_target", slot=slot, index_in_block=k, block_tx_count=n_block,
                     leader=plan["target_identity"], fee=i.probe["total_fee"], cost_units=i.probe["cost"])
        elif i.spill:
            o.update(status="spillover_other_leader", slot=first - 1, index_in_block=int(rng.integers(0, 300)),
                     block_tx_count=300, leader="OTHER_LEADER", fee=i.probe["total_fee"])
        else:
            o.update(status="expired_confirmed", slot=None, index_in_block=None, block_tx_count=None, leader=None)
        outcomes.append({"run_id": run_id, "outcome": o})
    window = {
        "run_id": run_id, "target_identity": plan["target_identity"], "client_id": target["client_id"],
        "ingress": target["ingress"], "seq": plan["seq"], "stage": plan["stage"], "kit": plan["kit"],
        "regime": plan["regime"], "burst_offset_ms": plan["burst_offset_ms"], "window_first_slot": first,
        "window_last_slot": first + 3, "connect": {"error": None}, "sent_ok": len(items), "not_sent": 0,
    }
    return probes, window, outcomes


# ---------------------------------------------------------------- whole run
def simulate(design_path: Path, targets_path: Path, out_dir: Path, params: Params, stage: int | None = 1,
             windows_per_target: int | None = None) -> Path:
    rng = np.random.default_rng(params.seed)
    targets = {t["identity"]: t for t in json.loads(Path(targets_path).read_text())}
    plans = [json.loads(l) for l in Path(design_path).read_text().splitlines() if l.strip()]
    if stage is not None:
        plans = [pl for pl in plans if pl["stage"] == stage]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"sim-{params.scenario}-{params.seed}"
    counts: dict[str, int] = {}
    slot = 460_100_000
    with (out_dir / "probes.jsonl").open("w") as fp, (out_dir / "windows.jsonl").open("w") as fw, \
            (out_dir / "outcomes.jsonl").open("w") as fo:
        for pl in plans:
            t = pl["target_identity"]
            if windows_per_target is not None and counts.get(t, 0) >= windows_per_target:
                continue
            counts[t] = counts.get(t, 0) + 1
            slot += 4 * int(rng.integers(5, 60))
            pl = dict(pl, window_first_slot=slot)
            probes, window, outcomes = simulate_window(pl, targets[t], params, rng, run_id)
            for x in probes:
                fp.write(json.dumps(x) + "\n")
            fw.write(json.dumps(window) + "\n")
            for x in outcomes:
                fo.write(json.dumps(x) + "\n")
    (out_dir / "target_states.jsonl").write_text("")
    (out_dir / "run_start.json").write_text(json.dumps({
        "run_id": run_id, "mode": "simulated", "stage": stage, "scenario": params.scenario,
        "params": {k: v for k, v in params.__dict__.items()}, "design_file": str(design_path),
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
    simulate(a.design, a.targets, a.out, Params(a.scenario, a.seed, a.landing, a.jitter_ms, t_ms=a.t_ms),
             a.stage, a.windows_per_target)


if __name__ == "__main__":
    main()
