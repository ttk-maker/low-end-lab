$ErrorActionPreference = 'Stop'
$analysisRoot = $PSScriptRoot
$analysisVenv = Join-Path $analysisRoot '.venv'
py -3.10 -m venv --without-pip $analysisVenv
if ($LASTEXITCODE -ne 0) { throw 'Creating the Python 3.10 virtual environment failed.' }
$analysisPython = Join-Path $analysisVenv 'Scripts/python.exe'
py -m pip --python $analysisPython install pip -r (Join-Path $analysisRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Installing audio dependencies failed.' }
$analysisModels = Join-Path $analysisRoot 'models'
New-Item -ItemType Directory -Force -Path $analysisModels | Out-Null
$analysisCheckpoint = Join-Path $analysisModels 'small0.ckpt'
if (-not (Test-Path -LiteralPath $analysisCheckpoint)) {
    curl.exe -f -L 'https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp/small0.ckpt' -o $analysisCheckpoint
    if ($LASTEXITCODE -ne 0) { throw 'Downloading the official Beat This! checkpoint failed.' }
}
$chordCheckpoint = Join-Path $analysisModels 'btc_model_large_voca.pt'
if (-not (Test-Path -LiteralPath $chordCheckpoint)) {
    curl.exe -f -L 'https://raw.githubusercontent.com/jayg996/BTC-ISMIR19/master/test/btc_model_large_voca.pt' -o $chordCheckpoint
    if ($LASTEXITCODE -ne 0) { throw 'Downloading the official BTC checkpoint failed.' }
}
$chordHash = (Get-FileHash -LiteralPath $chordCheckpoint -Algorithm SHA256).Hash.ToLower()
if ($chordHash -ne '1673d23f8f9a55ae7f9e8b80a51da616debb22675b8d8b67ea6ce0ef37b0ab51') { throw 'BTC checkpoint checksum mismatch.' }
Write-Output 'Ready. Run the launcher in the parent folder.'
