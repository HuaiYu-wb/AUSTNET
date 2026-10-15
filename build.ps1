# 打包 AUSTNET：先编单文件 exe，再用 Inno Setup 打安装包。
#
#   .\build.ps1                 完整打包
#   .\build.ps1 -SkipInstaller  只出 exe

param(
    [switch]$SkipInstaller
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
if (-not (Test-Path $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}

Write-Host '[1/4] 生成图标'
& $python tools\make_icons.py
if ($LASTEXITCODE -ne 0) { throw '图标生成失败' }

Write-Host '[2/4] PyInstaller 打包'
& $python -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name AUSTNET `
    --icon assets\austnet-ok.ico `
    --add-data 'assets;assets' `
    --exclude-module PIL `
    --version-file installer\version_info.txt `
    austnet.pyw
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller 打包失败' }

if ($SkipInstaller) { return }

Write-Host '[3/4] 查找 Inno Setup'
$iscc = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
    (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
    (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe')
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw '没找到 ISCC.exe，请先安装 Inno Setup 6' }

# .iss 含中文，Inno Setup 要求 UTF-8 带 BOM；编辑器存丢 BOM 就会变乱码，这里兜一下。
$issPath = Resolve-Path 'installer\AUSTNET.iss'
$issBytes = [IO.File]::ReadAllBytes($issPath)
if ($issBytes.Length -lt 3 -or $issBytes[0] -ne 0xEF -or $issBytes[1] -ne 0xBB -or $issBytes[2] -ne 0xBF) {
    Write-Host '      补写 .iss 的 UTF-8 BOM'
    $issText = [IO.File]::ReadAllText($issPath, [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText($issPath, $issText, [Text.UTF8Encoding]::new($true))
}

Write-Host '[4/4] 编译安装包'
& $iscc 'installer\AUSTNET.iss'
if ($LASTEXITCODE -ne 0) { throw '安装包编译失败' }

Write-Host ''
Write-Host '产物：'
Get-ChildItem dist -Filter *.exe |
    Select-Object Name, @{ n = 'MB'; e = { [math]::Round($_.Length / 1MB, 1) } }
