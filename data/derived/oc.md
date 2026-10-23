| Scenario | True mechanism | Correct | Honest non-claim | Wrong | Any core target wrong (≤ 95 % bound) | Robust wrong | Controls pass | Median C1 pairs |
|---|---|---|---|---|---|---|---|---|
| `reward_cost_greedy` | reward_cost | 99 % | 1 % | 0 % | 0 % (≤ 3 %) | 0 % | 100 % | 35 |
| `reward_cost_batch_20` | reward_cost | 99 % | 1 % | 0 % | 0 % (≤ 3 %) | 0 % | 100 % | 36 |
| `cu_price_batch_20` | cu_price | 99 % | 1 % | 0 % | 0 % (≤ 3 %) | 0 % | 100 % | 36 |
| `cu_price_batch_50` | cu_price | 99 % | 1 % | 0 % | 0 % (≤ 3 %) | 0 % | 100 % | 35 |
| `cu_price_fifo_tie` | cu_price | 100 % | 0 % | 0 % | 0 % (≤ 3 %) | 0 % | 100 % | 34 |
| `lamport_fee_batch_50` | lamport_fee | 99 % | 1 % | 0 % | 0 % (≤ 3 %) | 0 % | 100 % | 35 |
| `fifo` | fifo | 96 % | 2 % | 1 % | 5 % (≤ 10 %) | 0 % | 100 % | 34 |
| `random` | none | 99 % | 1 % | 0 % | 0 % (≤ 3 %) | 0 % | 100 % | 35 |
| `streaming_pacing` | reward_cost | 100 % | 0 % | 0 % | 0 % (≤ 3 %) | 0 % | 100 % | 36 |
| `fifo_reorder` | none | 99 % | 0 % | 0 % | 1 % (≤ 5 %) | 0 % | 100 % | 36 |
| `label_blind_reorder` | fifo / partial:fifo | 0 % | 100 % | 0 % | 0 % (≤ 3 %) | 0 % | 100 % | 35 |
| `selective_drop_cu_price` | cu_price | 100 % | 0 % | 0 % | 0 % (≤ 3 %) | 0 % | 100 % | 21 |
| `correlated_pair_loss` | unidentified:selection | 100 % | 0 % | 0 % | 0 % (≤ 3 %) | 0 % | 100 % | 27 |
| `balanced_double_loss` | none / unidentified / unidentified:selection | 1 % | 0 % | 99 % | 100 % (≤ 100 %) | 0 % | 100 % | 22 |
| `mode_switch_rc_fifo` | mixed:fifo+reward_cost / partial:reward_cost / partial:fifo | 16 % | 84 % | 0 % | 2 % (≤ 6 %) | 0 % | 100 % | 35 |
| `low_landing_reward_cost` | reward_cost | 51 % | 49 % | 0 % | 0 % (≤ 3 %) | 0 % | 83 % | 13 |
| `low_landing_cu_price` | cu_price | 79 % | 21 % | 0 % | 0 % (≤ 3 %) | 0 % | 83 % | 13 |
