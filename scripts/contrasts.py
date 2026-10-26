"""Contrast library for PLAN v2 §2.3: prints each probe's fee, Agave cost and priority, and what each rule predicts.

Cost model (agave v4.3.2 cost-model, firedancer v26.10.4 fd_pack_cost.h):
  720 per signature + 300 per writable account + instruction-data bytes / 4
  + requested CU limit + 8 per 32 KiB page of the requested loaded-accounts-data limit.
Priority (agave core/src/transaction_priority.rs): floor(reward * 1e6 / (cost + 1)),
  reward = priority fee + 50 % of the 5000-lamport signature fee.
The atom has 1 signature, 2 writable accounts (payer, lock) and 31 bytes of instruction data.
"""
import math

SIG_COST, WRITE_LOCK_COST = 720, 300
IX_DATA_BYTES = 5 + 9 + 5 + 12  # SetComputeUnitLimit, SetComputeUnitPrice, SetLoadedAccountsDataSizeLimit, Transfer
K32, M64 = 32 * 1024, 64 * 1024 * 1024


def priority_fee(L, p):
    return math.ceil(L * p / 1_000_000)


def cost(L, D):
    return SIG_COST + 2 * WRITE_LOCK_COST + IX_DATA_BYTES // 4 + L + 8 * math.ceil(D / K32)


def priority(L, p, D):
    return (2500 + priority_fee(L, p)) * 1_000_000 // (cost(L, D) + 1)


PROBES = {
    "A": (1000, 1_000_000, K32),
    "B": (3000, 500_000, K32),
    "A'": (1000, 1_000_000, M64),
    "hi": (1000, 3_000_000, K32),
    "lo": (1000, 1_000_000, M64),
    "Y": (3000, 2_000_000, K32),  # Study 3
}
CONTRASTS = {"C1": ("A", "B"), "C2": ("A'", "B"), "C3": ("A", "A'"), "dominance": ("hi", "lo"),
             "C4": ("Y", "A"), "C5": ("hi", "A")}
RULES = {
    "cu_price": lambda t: t[1],
    "lamport_fee": lambda t: priority_fee(t[0], t[1]),
    "reward_cost": lambda t: priority(*t),
    "cost_only": lambda t: -cost(t[0], t[2]),  # cheapest first: matches reward_cost on C1-C3, not on C4 / C5
}


def predict(x, y):
    out = {}
    for name, key in RULES.items():
        kx, ky = key(PROBES[x]), key(PROBES[y])
        out[name] = x if kx > ky else y if ky > kx else "tie"
    return out


if __name__ == "__main__":
    for n, (L, p, D) in PROBES.items():
        print(f"{n:3} L={L:5} p={p:>9} D={'32KiB' if D == K32 else '64MiB'} prio_fee={priority_fee(L, p):5} "
              f"total_fee={5000 + priority_fee(L, p):5} cost={cost(L, D):6} P={priority(L, p, D):>10,}")
    for c, (x, y) in CONTRASTS.items():
        print(c, f"{x} vs {y}", predict(x, y))
