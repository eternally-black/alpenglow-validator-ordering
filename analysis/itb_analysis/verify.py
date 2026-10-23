"""Claim ledger: re-derive every chain-verifiable fact behind the results (PLAN §11).

For each landed probe:
- the block at `slot` contains `signature` at `index_in_block`;
- the transaction decodes to the claimed probe: SetComputeUnitLimit(L), SetComputeUnitPrice(p),
  SetLoadedAccountsDataSizeLimit(D), System transfer of 0 lamports from the payer to the claimed lock;
- the charged fee equals 5000 + ceil(L·p/1e6);
- the slot's leader is the target.

Sources: `--source chain` re-fetches blocks over JSON-RPC (default public mainnet, rate-limited, so a sample);
`--source archive` reads the raw blocks committed with each run. Facts that are only locally recorded (send
timestamps, transport events) are listed separately and are not "verified" by this tool.
"""

from __future__ import annotations

import base64
import json
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


def b58decode(s: str) -> bytes:
    n = 0
    for ch in s:
        n = n * 58 + B58.index(ch)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    pad = len(s) - len(s.lstrip("1"))
    return b"\x00" * pad + raw


def decode_probe(tx: dict) -> dict:
    """Decodes the probe atom from a `getBlock` (encoding=json) transaction entry."""
    msg = tx["transaction"]["message"]
    keys = msg["accountKeys"]
    out = {"payer": keys[0], "cu_limit": None, "cu_price": None, "loaded_data_limit": None, "lock": None, "lamports": None}
    for ix in msg["instructions"]:
        program = keys[ix["programIdIndex"]]
        data = b58decode(ix["data"])
        if program == COMPUTE_BUDGET and data:
            tag = data[0]
            if tag == 2 and len(data) >= 5:
                out["cu_limit"] = int.from_bytes(data[1:5], "little")
            elif tag == 3 and len(data) >= 9:
                out["cu_price"] = int.from_bytes(data[1:9], "little")
            elif tag == 4 and len(data) >= 5:
                out["loaded_data_limit"] = int.from_bytes(data[1:5], "little")
        elif program == SYSTEM and len(data) >= 12 and int.from_bytes(data[0:4], "little") == 2:
            out["lock"] = keys[ix["accounts"][1]]
            out["lamports"] = int.from_bytes(data[4:12], "little")
    return out


@dataclass
class Rpc:
    url: str
    min_interval_s: float = 1.7  # public mainnet allows ~6 getBlock per 10 s

    def __post_init__(self):
        self._last = 0.0

    def call(self, method: str, params: list):
        for attempt in range(8):
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
            if o.get("status") in ("landed_target", "spillover_same_validator_later", "spillover_other_leader"):
                claims.append((d, probes.get(o["probe_id"]), o))
    if sample is not None and len(claims) > sample:
        random.Random(seed).shuffle(claims)
        claims = claims[:sample]
    rpc = Rpc(rpc_url) if source == "chain" else None
    blocks: dict[int, dict] = {}
    leaders: dict[int, str] = {}
    results = []
    for d, probe, o in claims:
        slot = o["slot"]
        r = {"probe_id": o["probe_id"], "signature": o["signature"], "slot": slot, "claimed_index": o["index_in_block"], "checks": {}}
        if slot not in blocks:
            if source == "chain":
                blocks[slot] = rpc.call("getBlock", [slot, {"encoding": "json", "maxSupportedTransactionVersion": 1,
                                                            "transactionDetails": "full", "rewards": False}])
                leaders[slot] = rpc.call("getSlotLeaders", [slot, 1])[0]
            else:
                blocks[slot] = _block_from_archive(d, slot)
        block = blocks[slot]
        if block is None:
            r["checks"]["block_available"] = False
            results.append(r)
            continue
        txs = block["transactions"]
        idx = o["index_in_block"]
        sig_at = txs[idx]["transaction"]["signatures"][0] if idx is not None and idx < len(txs) else None
        r["checks"]["signature_at_index"] = sig_at == o["signature"]
        tx = next((t for t in txs if t["transaction"]["signatures"][0] == o["signature"]), None)
        if tx is not None and probe is not None:
            dec = decode_probe(tx)
            t = probe["template"]
            r["checks"]["template_matches"] = (dec["cu_limit"], dec["cu_price"], dec["loaded_data_limit"]) == (
                t["cu_limit"], t["cu_price_micro_lamports"], t["loaded_data_limit"])
            r["checks"]["lock_matches"] = dec["lock"] == probe.get("lock", dec["lock"]) and dec["lamports"] == 0
            r["checks"]["payer_matches"] = dec["payer"] == probe.get("payer", dec["payer"])
            expected_fee = 5000 + math.ceil(t["cu_limit"] * t["cu_price_micro_lamports"] / 1_000_000)
            r["checks"]["fee_matches"] = tx["meta"]["fee"] == expected_fee
            if source == "chain":
                r["checks"]["leader_is_target"] = (leaders[slot] == probe["target_identity"]) == (o["status"] != "spillover_other_leader")
        else:
            r["checks"]["transaction_found"] = False
        r["ok"] = all(r["checks"].values())
        results.append(r)
    ok = sum(1 for r in results if r.get("ok"))
    return {"source": source, "claims_checked": len(results), "claims_ok": ok, "results": results}


def print_ledger(report: dict) -> None:
    print(f"{'probe_id':<34} {'slot':>11} {'idx':>5}  checks")
    for r in report["results"]:
        flags = " ".join(f"{k}={'✓' if v else '✗'}" for k, v in r["checks"].items())
        print(f"{r['probe_id']:<34} {r['slot']:>11} {str(r['claimed_index']):>5}  {flags}")
    print(f"\n{report['claims_ok']}/{report['claims_checked']} claims verified ({report['source']})")
