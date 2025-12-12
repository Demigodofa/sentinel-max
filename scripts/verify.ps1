param(
    [string]$PythonPath = "python"
)

$ErrorActionPreference = "Stop"
$results = @()

function Invoke-Step {
    param (
        [string]$Name,
        [ScriptBlock]$Action
    )

    Write-Host "== $Name =="
    try {
        & $Action
        $results += @{ Name = $Name; Success = $true }
    }
    catch {
        Write-Host "[$Name] failed" -ForegroundColor Red
        Write-Host $_
        $results += @{ Name = $Name; Success = $false }
    }
    Write-Host ""
}

Invoke-Step -Name "Compileall" -Action { & $PythonPath -m compileall sentinel }
Invoke-Step -Name "Pytest smoke" -Action { pytest sentinel/tests/test_conversation_pipeline.py sentinel/tests/test_project_memory_subsystem.py }

if ($results.Where({ -not $_.Success }).Count -eq 0) {
    Write-Host "ALL CHECKS PASSED" -ForegroundColor Green
}
else {
    Write-Host "ONE OR MORE CHECKS FAILED" -ForegroundColor Red
    exit 1
}
