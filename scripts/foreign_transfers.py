#!/usr/bin/env python3
"""List transactions that touched the campaign's owned accounts but are not ours (not in the spend ledger).

    PYTHONPATH=analysis python scripts/foreign_transfers.py [--ledger state/ledger.sqlite] [--keys keys]

Active Solana addresses attract spam "dust" transfers. They raise our balances, so reconciliation stays safe (the
on-chain drop is smaller than the fees charged). Each one is recorded with `itb ledger --add-deposit-lamports N` to keep
the accounting exact; this script finds them. It reads RPC_URL from .env and prints only signatures, slots and
lamport deltas — never the URL.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sqlite3

import requests

from itb_analysis.verify import b58encode


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ledger", default="state/ledger.sqlite")
    ap.add_argument("--keys", default="keys")
    a = ap.parse_args()
    env = dict(l.split("=", 1) for l in pathlib.Path(".env").read_text().splitlines() if "=" in l and not l.startswith("#"))
    url = env["RPC_URL"].strip()

    def rpc(method, params):
        return requests.post(url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=30).json().get("result")

    keys = pathlib.Path(a.keys)
    owned = [b58encode(bytes(json.loads((keys / "master.json").read_text()))[32:64])] + [
        b58encode(bytes(json.loads(p.read_text()))[32:64]) for p in sorted((keys / "payers").glob("*.json"))]
    db = sqlite3.connect(f"file:{a.ledger}?mode=ro", uri=True)
    ours = {r[0] for r in db.execute("SELECT signature FROM reservations")}
    seen = set()
    for acct in owned:
        for s in rpc("getSignaturesForAddress", [acct, {"limit": 1000}]) or []:
            sig = s["signature"]
            if sig in ours or sig in seen:
                continue
            seen.add(sig)
            tx = rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])
            ks = [k["pubkey"] for k in tx["transaction"]["message"]["accountKeys"]]
            delta = {k: tx["meta"]["postBalances"][i] - tx["meta"]["preBalances"][i] for i, k in enumerate(ks) if k in owned}
            print(json.dumps({"signature": sig, "slot": s["slot"], "fee_payer": ks[0], "owned_deltas": delta}))


if __name__ == "__main__":
    main()
