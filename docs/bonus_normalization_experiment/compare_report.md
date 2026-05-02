# Normalization comparison report

Versions present: v0=baseline, v1=Claude, v2=NOT YET CREATED

## Counts

| version | entries | lines | schema |
|---------|---------|-------|--------|
| v0 baseline      | 153 | 2956 | STATUS:           OK — schema clean. |
| v1 Claude        | 153 | 2947 | STATUS:           OK — schema clean. |
| v2 round-robin   | (not yet created — run `run_pass_b.ps1` then save the result here) | | |

## Diff summaries

- v0 → v1 (Claude): +11 / 20 (added/removed lines)

## Where the two passes agree

(intersection requires v2 — run the round-robin pass and save the
result as `BUG_BIBLE.v2_round_robin.yaml` next to this report,
then re-run `python compare_passes.py`.)
