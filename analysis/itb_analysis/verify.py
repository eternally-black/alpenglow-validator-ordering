"""Claim ledger: re-derive every chain-verifiable fact behind the results (PLAN §11).

For each claimed landing of a probe:
1. **Binding.** The signed bytes we logged before sending (`probes.jsonl` `wire_base64`) carry a valid ed25519
   signature by the probe's payer, and that signature is the one claimed in the outcome.
2. **Atom.** Those bytes decode to exactly the declared probe: a legacy message with header (1, 0, 2), the payer,
   the lock and the two programs, and exactly four instructions in order — SetComputeUnitLimit(L),
   SetComputeUnitPrice(p), SetLoadedAccountsDataSizeLimit(D), System transfer of 0 lamports payer → lock — with L, p,
   D, payer and lock equal to the logged design values.
3. **Chain.** The block at the claimed slot contains that signature at the claimed (non-negative) index, its message
   equals the signed one field by field, and the charged fee is 5000 + ⌈L·p/10⁶⌉.
4. **Attribution.** The slot's leader (the "Fee" reward recipient in the block, cross-checked with getSlotLeaders on
   chain) matches the claimed status, and a `landed_target` slot lies inside the claimed window.

Sources: `chain` re-fetches blocks over JSON-RPC (default public mainnet, rate-limited, so a sample);
`archive` reads the raw blocks committed with each run. Send timestamps and transport events are local records and
are not "verified" by this tool. Checking zero claims is a failure, not a pass.
"""

from __future__ import annotations

import base64
import math
import random
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from .load import read_jsonl, read_zst_json

COMPUTE_BUDGET = "ComputeBudget111111111111111111111111111111"
SYSTEM = "11111111111111111111111111111111"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
LANDED_CLAIMS = ("landed_target", "spillover_same_validator_other_window", "spillover_other_leader")


def b58decode(s: str) -> bytes:
    n = 0
    for ch in s:
        n = n * 58 + B58.index(ch)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\x00" * (len(s) - len(s.lstrip("1"))) + raw


def b58encode(b: bytes) -> str:
    n = int.from_bytes(b, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = B58[r] + out
    return "1" * (len(b) - len(b.lstrip(b"\x00"))) + out


def _compact_u16(buf: bytes, i: int) -> tuple[int, int]:
    val, shift = 0, 0
    while True:
        byte = buf[i]
        i += 1
        val |= (byte & 0x7F) << shift
        if byte & 0x80 == 0:
            return val, i
        shift += 7


def parse_legacy_tx(wire: bytes) -> dict:
    """Parses a bincode-serialised legacy transaction (what we sent)."""
    n_sigs, i = _compact_u16(wire, 0)
    sigs = [wire[i + 64 * k: i + 64 * (k + 1)] for k in range(n_sigs)]
    i += 64 * n_sigs
    message = wire[i:]
    if message[0] & 0x80:
        raise ValueError("versioned message; probes are legacy")
    header = tuple(message[0:3])
    j = 3
    n_keys, j = _compact_u16(message, j)
    keys = [message[j + 32 * k: j + 32 * (k + 1)] for k in range(n_keys)]
    j += 32 * n_keys
    blockhash = message[j: j + 32]
    j += 32
    n_ix, j = _compact_u16(message, j)
    ixs = []
    for _ in range(n_ix):
        prog = message[j]
        j += 1
        n_acc, j = _compact_u16(message, j)
        accs = list(message[j: j + n_acc])
        j += n_acc
        n_data, j = _compact_u16(message, j)
        data = message[j: j + n_data]
        j += n_data
        ixs.append({"programIdIndex": prog, "accounts": accs, "data": data})
    if j != len(message):
        raise ValueError("trailing bytes in message")
    return {"signatures": sigs, "message_bytes": message, "header": header, "keys": [b58encode(k) for k in keys],
            "blockhash": b58encode(blockhash), "instructions": ixs}


def check_atom(tx: dict, probe: dict) -> dict[str, bool]:
    """Exact probe-atom checks on the parsed signed bytes."""
    t = probe["template"]
    keys, ixs = tx["keys"], tx["instructions"]
    checks = {"header_1_0_2": tx["header"] == (1, 0, 2), "four_keys": len(keys) == 4, "four_instructions": len(ixs) == 4}
    if not (checks["four_keys"] and checks["four_instructions"]):
        return checks
    checks["payer_is_key0"] = keys[0] == probe.get("payer")
    checks["lock_is_key1"] = keys[1] == probe.get("lock")
    checks["programs"] = set(keys[2:]) == {COMPUTE_BUDGET, SYSTEM}
    prog = [keys[ix["programIdIndex"]] for ix in ixs]
    d = [ix["data"] for ix in ixs]
    checks["instruction_programs_in_order"] = prog == [COMPUTE_BUDGET, COMPUTE_BUDGET, COMPUTE_BUDGET, SYSTEM]
    checks["instruction_lengths"] = [len(x) for x in d] == [5, 9, 5, 12]
    if checks["instruction_programs_in_order"] and checks["instruction_lengths"]:
        checks["cu_limit"] = d[0][0] == 2 and int.from_bytes(d[0][1:5], "little") == t["cu_limit"]
        checks["cu_price"] = d[1][0] == 3 and int.from_bytes(d[1][1:9], "little") == t["cu_price_micro_lamports"]
        checks["loaded_data_limit"] = d[2][0] == 4 and int.from_bytes(d[2][1:5], "little") == t["loaded_data_limit"]
        checks["transfer_0_payer_to_lock"] = (
            int.from_bytes(d[3][0:4], "little") == 2 and int.from_bytes(d[3][4:12], "little") == 0 and ixs[3]["accounts"] == [0, 1]
        )
    return checks


def check_signature(tx: dict, payer: str, claimed_signature: str) -> dict[str, bool]:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    sig = tx["signatures"][0] if tx["signatures"] else b""
    ok = False
    try:
        Ed25519PublicKey.from_public_bytes(b58decode(payer)).verify(sig, tx["message_bytes"])
        ok = True
    except (InvalidSignature, ValueError):
        ok = False
    return {"ed25519_valid": ok, "signature_matches_claim": b58encode(sig) == claimed_signature}


def check_onchain_message(onchain: dict, tx: dict) -> bool:
    """The block's JSON message equals the signed one, field by field."""
    m = onchain["transaction"]["message"]
    h = m.get("header", {})
    same_header = (h.get("numRequiredSignatures"), h.get("numReadonlySignedAccounts"), h.get("numReadonlyUnsignedAccounts")) == tx["header"]
    same_keys = m.get("accountKeys") == tx["keys"]
    same_hash = m.get("recentBlockhash") == tx["blockhash"]
    ixs = m.get("instructions", [])
    same_ix = len(ixs) == len(tx["instructions"]) and all(
        a.get("programIdIndex") == b["programIdIndex"] and a.get("accounts") == b["accounts"] and b58decode(a.get("data", "")) == b["data"]
        for a, b in zip(ixs, tx["instructions"])
    )
    return bool(same_header and same_keys and same_hash and same_ix and onchain.get("version", "legacy") in ("legacy", None))


def block_leader(block: dict) -> str | None:
    for r in block.get("rewards") or []:
        if r.get("rewardType") == "Fee":
            return r.get("pubkey")
    return None


@dataclass
class Rpc:
    url: str
    min_interval_s: float = 1.7  # public mainnet allows ~6 getBlock per 10 s

    def __post_init__(self):
        self._last = 0.0

    def call(self, method: str, params: list):
        for _ in range(8):
            wait = self._last + self.min_interval_s - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            r = requests.post(self.url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=60)
            if r.status_code == 429:
                time.sleep(float(r.headers.get("retry-after", 10)))
                continue
            r.raise_for_status()
            body = r.json()
            if "error" in body:
                raise RuntimeError(f"{method}: {body['error']}")
            return body["result"]
        raise RuntimeError(f"{method}: still throttled after retries")


def _block_from_archive(run_dir: Path, slot: int):
    p = run_dir / "blocks" / f"{slot}.json.zst"
    return read_zst_json(p) if p.exists() else None


def verify(run_dirs: list[Path], source: str = "archive", rpc_url: str = "https://api.mainnet-beta.solana.com",
           sample: int | None = None, seed: int = 0) -> dict:
    claims = []
    for d in run_dirs:
        probes = {p["probe_id"]: p for p in read_jsonl(d / "probes.jsonl")}
        for row in read_jsonl(d / "outcomes.jsonl"):
            o = row.get("outcome", row)
            if o.get("status") in LANDED_CLAIMS:
                claims.append((d, probes.get(o["probe_id"]), o))
    if sample is not None and len(claims) > sample:
        random.Random(seed).shuffle(claims)
        claims = claims[:sample]
    rpc = Rpc(rpc_url) if source == "chain" else None
    blocks: dict[int, dict] = {}
    leaders: dict[int, str] = {}
    results = []
    for d, probe, o in claims:
        slot, idx = o.get("slot"), o.get("index_in_block")
        r = {"probe_id": o["probe_id"], "signature": o["signature"], "status": o["status"], "slot": slot, "claimed_index": idx, "checks": {}}
        c = r["checks"]
        c["probe_record_exists"] = probe is not None
        c["signature_bound_to_probe"] = probe is not None and probe.get("signature") == o["signature"]
        c["index_nonnegative"] = isinstance(idx, int) and idx >= 0
        if probe is None or not isinstance(slot, int):
            r["ok"] = False
            results.append(r)
            continue
        try:
            tx = parse_legacy_tx(base64.b64decode(probe["wire_base64"]))
            c |= check_signature(tx, probe.get("payer", ""), o["signature"])
            c |= check_atom(tx, probe)
        except Exception as e:  # malformed bytes are a failed claim, not a crash
            c["signed_bytes_parse"] = False
            r["error"] = str(e)
            tx = None
        if slot not in blocks:
            if source == "chain":
                blocks[slot] = rpc.call("getBlock", [slot, {"encoding": "json", "maxSupportedTransactionVersion": 1,
                                                            "transactionDetails": "full", "rewards": True}])
                leaders[slot] = rpc.call("getSlotLeaders", [slot, 1])[0]
            else:
                blocks[slot] = _block_from_archive(d, slot)
        block = blocks[slot]
        c["block_available"] = block is not None
        if block is not None:
            txs = block["transactions"]
            at = txs[idx] if c["index_nonnegative"] and idx < len(txs) else None
            c["signature_at_index"] = at is not None and at["transaction"]["signatures"][0] == o["signature"]
            if at is not None and tx is not None:
                c["onchain_message_equals_signed"] = check_onchain_message(at, tx)
                t = probe["template"]
                c["fee"] = at["meta"]["fee"] == 5000 + math.ceil(t["cu_limit"] * t["cu_price_micro_lamports"] / 1_000_000)
            leader = block_leader(block)
            if source == "chain":
                c["leader_rewards_matches_schedule"] = leader == leaders[slot]
            target = probe["target_identity"]
            in_window = probe["window_first_slot"] <= slot <= probe["window_last_slot"]
            if o["status"] == "landed_target":
                c["leader_is_target"] = leader == target
                c["slot_in_claimed_window"] = in_window
            elif o["status"] == "spillover_same_validator_other_window":
                c["leader_is_target"] = leader == target
                c["slot_outside_claimed_window"] = not in_window
            else:
                c["leader_is_not_target"] = leader is not None and leader != target
        r["ok"] = all(c.values())
        results.append(r)
    ok = sum(1 for r in results if r.get("ok"))
    return {"source": source, "claims_checked": len(results), "claims_ok": ok, "results": results,
            "passed": len(results) > 0 and ok == len(results)}


def print_ledger(report: dict) -> None:
    print(f"{'probe_id':<34} {'slot':>11} {'idx':>5}  result")
    for r in report["results"]:
        bad = [k for k, v in r["checks"].items() if not v]
        print(f"{r['probe_id']:<34} {str(r['slot']):>11} {str(r['claimed_index']):>5}  {'OK (' + str(len(r['checks'])) + ' checks)' if r.get('ok') else 'FAILED: ' + ', '.join(bad)}")
    if report["claims_checked"] == 0:
        print("\nNO CLAIMS CHECKED — verification did not cover anything (treated as failure)")
    else:
        print(f"\n{report['claims_ok']}/{report['claims_checked']} claims verified ({report['source']})")
