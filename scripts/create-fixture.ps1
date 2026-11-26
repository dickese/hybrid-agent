[CmdletBinding()]
param(
    [string]$Root = 'D:\tools\hybrid-agent\.runtime\fixtures',
    [string]$Name = ''
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($Name)) {
    $Name = 'fixture-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
}
if ($Name -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$') {
    throw "Fixture name is not safe: $Name"
}
$fixture = Join-Path $Root $Name
if (Test-Path -LiteralPath $fixture) {
    throw "Fixture already exists; choose a fresh name: $fixture"
}
New-Item -ItemType Directory -Path $fixture -Force | Out-Null
Push-Location $fixture
try {
    git init -b master | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'git init failed' }
    git config user.name 'Fixture'
    git config user.email 'fixture@example.invalid'
    [System.IO.File]::WriteAllText(
        (Join-Path $fixture 'add.py'),
        "def add(a, b): return a - b`n",
        (New-Object System.Text.UTF8Encoding($false))
    )
    [System.IO.File]::WriteAllText(
        (Join-Path $fixture 'test_add.py'),
        "from add import add; assert add(2, 3) == 5`n",
        (New-Object System.Text.UTF8Encoding($false))
    )
    git add add.py test_add.py
    git -c user.name=Fixture -c user.email=fixture@example.invalid commit -m 'fixture baseline' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'fixture commit failed' }
    $head = (git rev-parse HEAD).Trim()
    $branch = (git branch --show-current).Trim()
    python -B test_add.py
    $testExit = $LASTEXITCODE
    if ($testExit -eq 0) { throw 'fixture baseline test unexpectedly passed' }
    [pscustomobject]@{
        status = 'PASS'
        fixture = $fixture
        branch = $branch
        head = $head
        baseline_test_exit = $testExit
    } | ConvertTo-Json -Compress
}
finally {
    Pop-Location
}
