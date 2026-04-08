# ComfyUI Custom Node Bug Bible

**By Jeffrey A. Brick** · v1.2 SIGNAL LOST Edition · April 2026

A machine-readable bug-and-fix database for ComfyUI custom node development. Every entry is a real failure mode encountered shipping production node packs (Goofer, ComfyUI-OldTimeRadio / SIGNAL LOST). Built to be loaded by AI coding assistants as a reference, with minimal token cost.

## Read This

- **[BUG_BIBLE.yaml](./BUG_BIBLE.yaml)** — the entire knowledge base. ~70 entries. Each entry: `id, area, symptom, cause, fix, verify, tags`. Greppable, parseable, no prose fluff.

## How To Use

**Humans:** open `BUG_BIBLE.yaml`, ctrl-F by `area:` (architecture, widgets, vram, transformers, git, workflow-json, llm, pool-sizing, etc.) or by `tags:`.

**AI assistants:** load `BUG_BIBLE.yaml` at the start of any ComfyUI custom-node task. Match the user's symptom against `symptom:` fields, then apply the `fix:`, then run `verify:`.

## Coverage Areas

architecture · windows · powershell · git · huggingface · python · cuda · transformers · widgets · loading · coordination · migration · naming · hidden-inputs · validation · list-execution · lazy · interrupt · combo · asyncio · headless · execution-order · vram · model-class · tensors · audio · video · audio-contract · memory · caching · paths · network · data · metadata · telemetry · workflow-json · safety · pool-sizing · regression · rng · deps · ai-autonomy · testing · encoding · sandbox · subprocess · discovery · pipeline-sync · io · output_node · llm · ai-continuity · hygiene · procedural

## Source Projects

- [ComfyUI-OldTimeRadio (SIGNAL LOST)](https://github.com/jbrick2070/ComfyUI-OldTimeRadio)
- Goofer node pack (internal)

## License

MIT. Use freely. If an entry helped you, the cost of admission is sending a new bug back as a YAML PR.
