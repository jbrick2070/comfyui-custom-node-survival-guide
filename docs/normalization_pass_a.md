# Pass A — Claude normalization report

Source: `BUG_BIBLE.yaml`
Total entries: 153

## Counts

- N2: 1
- N3: 9
- N4: 1

## Detail

N2 deduped tags: tags: [dependencies, audio-model, windows, dependencies, av, spacy, py…
N3 legacy_id: "NEW" → "" (×9)
N4 stripped trailing whitespace (×1 lines)

## Notes / non-actions

- N7 phase-grouping reorder: SKIPPED. Reordering 40+ entries to fully sort by phase would produce a large churny diff with no behavioral payoff. Validator reports `STATUS: OK` regardless of in-file order.
- Tag style: kebab-case AND snake_case both accepted by validator. Snake_case retained ONLY when the tag refers to a literal Python symbol (`output_node`, `is_changed`, `validate_inputs`, etc.). Natural-language phrases stay kebab-case.
- Legacy mapping-form (`12.NN:`) entries — already normalized to canonical list form in the prior session.
