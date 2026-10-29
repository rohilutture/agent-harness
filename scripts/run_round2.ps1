# Round 2: experiments added after round 1 showed (a) memory = 0% for every model, because models never call
# search_notes on their own, and (b) --budget / --llm-summary changed nothing, because the tasks that set their own
# context budget ignore --budget and nothing hit a compaction. Re-runnable: finished runs are skipped.
#   .\scripts\run_round2.ps1        (the gpt-4o-mini row needs $env:OPENAI_API_KEY)
$ErrorActionPreference = "Continue"
$env:PYTHONUTF8 = "1"
$py = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
Set-Location (Join-Path $PSScriptRoot "..")

function Run($name, $model, $extra) {
    if (Test-Path "results\$name.json") { Write-Host "== $name : already done, skipping"; return }
    Write-Host "== $name ($model) $(Get-Date -Format HH:mm:ss)"
    & $py -m evals.run_suite --model $model --trials 3 --name $name @extra
    Write-Host "== $name exit code $LASTEXITCODE"
}

# 1) Memory cue: list saved note keys in the system prompt (memory tasks only: t17 t18 t19)
$mem = @("--memory-index", "--only", "t17", "t18", "t19")
Run "qwen14b-memidx" "ollama:qwen2.5:14b" $mem
Run "llama8b-memidx" "ollama:llama3.1:8b" $mem
if ($env:OPENAI_API_KEY) { Run "gpt4omini-memidx" "openai:gpt-4o-mini" $mem } else { Write-Host "== OPENAI_API_KEY not set: skipping gpt-4o-mini" }

# 2) Compaction ablation with the budget forced on EVERY task so compaction actually triggers
Run "qwen14b-force1000" "ollama:qwen2.5:14b" @("--force-budget", "1000")
Run "qwen14b-force1000-llmsummary" "ollama:qwen2.5:14b" @("--force-budget", "1000", "--llm-summary")
Write-Host "== ROUND 2 DONE $(Get-Date -Format HH:mm:ss)"
