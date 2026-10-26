# design/

What each file is. The frozen files are hashed in a mainnet Memo; never edit them (a change after freezing is a
reported deviation).

| File | Role | Status |
|---|---|---|
| `targets.json` | Study 1 target list: identity, gossip client, ingress kind, tier, windows per kit | input of the frozen design |
| `design.jsonl` | Study 1 design, `itb design --seed 20261023`: 796 window plans | **frozen**, Memo [`5vRM47a8…QcyG`](https://explorer.solana.com/tx/5vRM47a8LfMLm1rQyQKdap292hmXk68kbad6Vf12nCxuzaZVGJSuL4g2DyLGNyZjsphPQLtVAqFkT3VxmRmLQcyg) |
| `campaign.json` | Study 1 manifest: core targets and groups, positive controls, design and genesis hashes, budget, cutoff | **frozen**, same Memo |
| `targets-study2.json` | Study 2 target list (adds the R and E kits) | input of the frozen design |
| `design-study2.jsonl` | Study 2 design, `itb design --study 2 --seed 20261025`: 570 window plans | **frozen**, Memo [`2T6ha9FD…D5ww`](https://explorer.solana.com/tx/2T6ha9FDfjp524NLBXFB2WRHvEaYAoQLKFcd7Pmwqmf8FzqHi3Pxf8TcacHm7ixiN8UoyQizReCSSmh5LAR7D5ww) |
| `campaign-study2.json` | Study 2 manifest: as above, plus the hypotheses with planned n, the Study 1 carry-over and the git tree of `analysis/` | **frozen**, same Memo |
| `targets-study3.json` | Study 3 target list: the six core targets, 32 windows each (N kit) | input of the frozen design |
| `design-study3.jsonl` | Study 3 design, `itb design --study 3 --seed 20261026`: 192 window plans, one C4 and one C5 pair each | **frozen**, Memo [`2C57e22K…beUz5`](https://explorer.solana.com/tx/2C57e22K29Hj1v5z1J3Wrp3gXS717KQBrzVuMgPQKWhMX7Lv38VZmsWybxHK8A5JErxRW3JHq6dkXRtisRxbeUz5) |
| `campaign-study3.json` | Study 3 manifest: as for Study 2, plus the Study 1 and Study 2 claims per core target with their source hashes | **frozen**, same Memo |
| `targets.pilot.json`, `design.pilot.jsonl` | first pilot (2026-10-24 07:18), calibration only | historical, not confirmatory |
| `targets.pilot2.json`, `design.pilot2.jsonl` | second pilot (07:59), after the execution fixes | historical, not confirmatory |
| `targets.draft.json`, `design.draft.jsonl` | draft design that the first simulation study ran on, before the freeze ([CAMPAIGN-LOG](../docs/CAMPAIGN-LOG.md), 2026-10-24 freeze entry) | historical; the simulation was rerun on the frozen design |

Check a frozen file against its Memo: `sha256sum design/design.jsonl design/campaign.json` (Study 1),
`sha256sum design/design-study2.jsonl design/campaign-study2.json` (Study 2),
`sha256sum docs/PREREGISTRATION-3.md design/design-study3.jsonl design/campaign-study3.json` (Study 3).
