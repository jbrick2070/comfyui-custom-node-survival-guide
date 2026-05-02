# Round-robin normalization consult — Pass B
#
# Run this from a fresh PowerShell window. It assumes you have at least
# one of OPENAI_API_KEY / GEMINI_API_KEY / NVIDIA_API_KEY set as a User
# env var (via `setx`).

cd /d C:\Users\jeffr\Documents\ComfyUI\comfyui-custom-node-survival-guide

# 1. Smoke-check the addon imports cleanly
python -c "from llm_round_robin import RoundRobinRunner, load_ladders; print('llm_round_robin OK')"

# 2. Run the round-robin consult on the prepared question
python -m llm_round_robin `
    --question docs/bonus_normalization_experiment/round_robin_question.md `
    --topic bible-normalization-pass-b `
    --needs reasoning+tools `
    --output-dir docs/bonus_normalization_experiment

# 3. Inspect the per-provider responses
$prefix = Get-Date -Format "yyyy-MM-dd"
$consult_dir = "docs\bonus_normalization_experiment"
Write-Host ""
Write-Host "Per-provider responses:"
Get-ChildItem $consult_dir -Filter "${prefix}-bible-normalization-pass-b__*" |
    Select-Object Name, Length, LastWriteTime |
    Format-Table

# 4. Open the synthesis (where all three provider answers are stitched
#    together with the to-decide checklist at the bottom)
Write-Host ""
Write-Host "Opening the synthesis markdown for review..."
$synth = Get-ChildItem $consult_dir -Filter "${prefix}-bible-normalization-pass-b__*_synthesis.md" |
    Select-Object -First 1
if ($synth) {
    Write-Host "  $($synth.FullName)"
    notepad $synth.FullName
} else {
    Write-Host "  no synthesis file found - check the per-round failure messages above"
}
