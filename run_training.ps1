# Run visibly in the VS Code integrated terminal. No test-set evaluation.
# Earlier prototype only. Full flowchart entry point: train_architecture.py.
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonExecutable = Join-Path $projectRoot '.venv_runtime/Scripts/python.exe'
$runName = 'run_' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmss_fffffffZ')
$runDirectory = Join-Path $projectRoot ('fedprox_outputs/' + $runName)
$registrationDirectory = Join-Path $projectRoot ('blockchain/registrations/' + $runName)
$logPath = Join-Path $projectRoot 'RUN_LOG.md'
Push-Location -LiteralPath $projectRoot
try {
    Add-Content -LiteralPath $logPath -Value "`n$([DateTime]::UtcNow.ToString('o')) run_training.ps1 start: output=$runDirectory; rounds20/local epochs3/seed42/mu0.01/workers0; no test evaluation; checkpoint registration follows success."
    Write-Host 'Starting FedProx: 20 rounds, 3 local epochs, seed 42, mu 0.01. Test evaluation OFF.'
    Write-Host 'This is the earlier prototype workflow; it does not run the full IPFS/peer architecture.'
    Write-Host "Run directory: $runDirectory"
    & $pythonExecutable -u (Join-Path $projectRoot 'train_fedprox.py') --dataset-root 'D:\dataset_patientsplit' --rounds 20 --local-epochs 3 --seed 42 --mu 0.01 --num-workers 0 --output-dir $runDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Training failed. Checkpoints and error logs were preserved; registration skipped.' }
    Write-Host 'Training completed. Preparing the selected checkpoint for local blockchain registration.'
    & $pythonExecutable -u (Join-Path $projectRoot 'blockchain/prepare_registration.py') --run-dir $runDirectory --output-dir $registrationDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Registration preparation failed; trained checkpoint is preserved.' }
    & $pythonExecutable -u (Join-Path $projectRoot 'blockchain/registry.py') deploy
    if ($LASTEXITCODE -ne 0) { throw 'Hardhat deployment unavailable; trained checkpoint is preserved. Restart the local node before retrying registration.' }
    & $pythonExecutable -u (Join-Path $projectRoot 'blockchain/registry.py') register --run-dir $runDirectory --registration-dir $registrationDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Registration failed; checkpoint and prepared manifest are preserved.' }
    & $pythonExecutable -u (Join-Path $projectRoot 'blockchain/registry.py') verify --run-dir $runDirectory --registration-dir $registrationDirectory
    if ($LASTEXITCODE -ne 0) { throw 'On-chain verification failed. Do not describe this registration as verified.' }
    Add-Content -LiteralPath $logPath -Value "$([DateTime]::UtcNow.ToString('o')) run_training.ps1 completed: trained checkpoint registered and verified; run=$runDirectory."
    Write-Host "Completed: checkpoint at $runDirectory\best_model.pt; blockchain receipt in $registrationDirectory."
} catch {
    Add-Content -LiteralPath $logPath -Value "$([DateTime]::UtcNow.ToString('o')) run_training.ps1 error: $($_.Exception.Message); run=$runDirectory."
    throw
} finally { Pop-Location }
