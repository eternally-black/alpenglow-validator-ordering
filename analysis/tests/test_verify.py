"""The verifier must accept a genuine probe claim and reject the reviewer's counterexamples."""

import base64
import copy
import json
import os

import zstandard
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from itb_analysis import verify as V

CB, SYS = V.COMPUTE_BUDGET, V.SYSTEM


def compact(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def make_probe(L=1000, p=1_000_000, D=32768):
    sk = Ed25519PrivateKey.generate()
    payer = sk.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    lock = os.urandom(32)
    keys = [payer, lock, V.b58decode(CB), V.b58decode(SYS)]
    blockhash = os.urandom(32)
    ixs = [
        (2, [], bytes([2]) + L.to_bytes(4, "little")),
        (2, [], bytes([3]) + p.to_bytes(8, "little")),
        (2, [], bytes([4]) + D.to_bytes(4, "little")),
        (3, [0, 1], (2).to_bytes(4, "little") + (0).to_bytes(8, "little")),
    ]
    msg = bytes([1, 0, 2]) + compact(len(keys)) + b"".join(keys) + blockhash + compact(len(ixs))
    for prog, accs, data in ixs:
        msg += bytes([prog]) + compact(len(accs)) + bytes(accs) + compact(len(data)) + data
    sig = sk.sign(msg)
    wire = compact(1) + sig + msg
    probe = {
        "probe_id": "T/000/c1/A", "target_identity": "TARGET", "signature": V.b58encode(sig), "payer": V.b58encode(payer),
        "lock": V.b58encode(lock), "template": {"cu_limit": L, "cu_price_micro_lamports": p, "loaded_data_limit": D},
        "window_first_slot": 100, "window_last_slot": 103, "wire_base64": base64.b64encode(wire).decode(),
    }
    onchain = {
        "transaction": {"signatures": [probe["signature"]], "message": {
            "header": {"numRequiredSignatures": 1, "numReadonlySignedAccounts": 0, "numReadonlyUnsignedAccounts": 2},
            "accountKeys": [V.b58encode(k) for k in keys], "recentBlockhash": V.b58encode(blockhash),
            "instructions": [{"programIdIndex": pr, "accounts": a, "data": V.b58encode(dt)} for pr, a, dt in ixs]}},
        "meta": {"fee": 5000 + (L * p + 999_999) // 1_000_000, "err": None},
        "version": "legacy",
    }
    return probe, onchain


def write_run(tmp, probe, onchain, outcome, leader="TARGET", slot=101):
    d = tmp / "run"
    (d / "blocks").mkdir(parents=True, exist_ok=True)
    (d / "probes.jsonl").write_text(json.dumps(probe) + "\n")
    (d / "outcomes.jsonl").write_text(json.dumps({"run_id": "r", "outcome": outcome}) + "\n")
    block = {"transactions": [{"transaction": {"signatures": ["other"]}, "meta": {"fee": 5000}}, onchain],
             "rewards": [{"pubkey": leader, "rewardType": "Fee", "lamports": 1}]}
    with (d / "blocks" / f"{slot}.json.zst").open("wb") as f:
        f.write(zstandard.ZstdCompressor().compress(json.dumps(block).encode()))
    return d


def outcome(probe, status="landed_target", slot=101, index=1):
    return {"probe_id": probe["probe_id"], "signature": probe["signature"], "status": status, "slot": slot, "index_in_block": index}


def test_genuine_claim_passes(tmp_path):
    probe, onchain = make_probe()
    rep = V.verify([write_run(tmp_path, probe, onchain, outcome(probe))])
    assert rep["passed"], rep["results"]


def test_extra_instruction_on_chain_is_rejected(tmp_path):
    probe, onchain = make_probe()
    bad = copy.deepcopy(onchain)
    bad["transaction"]["message"]["instructions"].append({"programIdIndex": 3, "accounts": [0, 1], "data": "3Bxs4h24hBtQy9rw"})
    rep = V.verify([write_run(tmp_path, probe, bad, outcome(probe))])
    assert not rep["passed"] and not rep["results"][0]["checks"]["onchain_message_equals_signed"]


def test_claim_outside_its_window_is_rejected(tmp_path):
    probe, onchain = make_probe()
    probe = dict(probe, window_first_slot=1100, window_last_slot=1103)
    rep = V.verify([write_run(tmp_path, probe, onchain, outcome(probe))])
    assert not rep["passed"] and not rep["results"][0]["checks"]["slot_in_claimed_window"]


def test_wrong_leader_and_negative_index_are_rejected(tmp_path):
    probe, onchain = make_probe()
    rep = V.verify([write_run(tmp_path, probe, onchain, outcome(probe), leader="SOMEONE_ELSE")])
    assert not rep["results"][0]["checks"]["leader_is_target"]
    rep = V.verify([write_run(tmp_path / "b", probe, onchain, outcome(probe, index=-1))])
    assert not rep["results"][0]["checks"]["index_nonnegative"]


def test_template_mismatch_is_rejected(tmp_path):
    probe, onchain = make_probe()
    probe = dict(probe, template=dict(probe["template"], cu_limit=3000))
    rep = V.verify([write_run(tmp_path, probe, onchain, outcome(probe))])
    assert not rep["results"][0]["checks"]["cu_limit"]


def test_empty_verification_is_not_a_pass(tmp_path):
    (tmp_path / "empty").mkdir()
    rep = V.verify([tmp_path / "empty"])
    assert rep["claims_checked"] == 0 and not rep["passed"]
