# Runs the full result set sequentially and unattended (Windows PowerShell / pwsh).
#   .\scripts\run_all.ps1
# Safe to re-run: a run whose results\<name>.json already exists is skipped.
# Needs Ollama with qwen2.5:14b and llama3.1:8b pulled; the gpt-4o-mini row needs $env:OPENAI_API_KEY.
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

# 1) Baselines per model
Run "qwen14b-baseline" "ollama:qwen2.5:14b" @()
Run "llama8b-baseline" "ollama:llama3.1:8b" @()
if ($env:OPENAI_API_KEY) { Run "gpt4omini-baseline" "openai:gpt-4o-mini" @() }
else { Write-Host "== OPENAI_API_KEY not set: skipping gpt-4o-mini" }

# 2) Ablations on the strongest local model
Run "qwen14b-llmsummary" "ollama:qwen2.5:14b" @("--llm-summary")
Run "qwen14b-budget4000" "ollama:qwen2.5:14b" @("--budget", "4000")
Run "qwen14b-noguard" "ollama:qwen2.5:14b" @("--no-injection-guard")

# 3) Regression-gate demo: removing the injection guard should be flagged (gate exits 1 on regression)
if ((Test-Path "results\qwen14b-baseline.json") -and (Test-Path "results\qwen14b-noguard.json")) {
    & $py -m evals.gate --baseline results/qwen14b-baseline.json --candidate results/qwen14b-noguard.json *> results\gate_demo.txt
    Write-Host "== gate demo exit code $LASTEXITCODE (1 = regression flagged)"
}
Write-Host "== ALL DONE $(Get-Date -Format HH:mm:ss)"
