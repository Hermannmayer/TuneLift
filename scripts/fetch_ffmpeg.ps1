<#
.SYNOPSIS
    把 ffmpeg.exe 下载到仓库根目录。

.DESCRIPTION
    ffmpeg 体积太大，不适合进版本库，所以 build.bat 需要它先在位。
    默认取 gyan.dev 的 essentials 静态构建：体积小、依赖少，够用。
    文件已经存在时直接跳过，方便反复调用。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/fetch_ffmpeg.ps1

.EXAMPLE
    # 换成自定义来源
    powershell -ExecutionPolicy Bypass -File scripts/fetch_ffmpeg.ps1 -Url https://example.com/ffmpeg.zip
#>
[CmdletBinding()]
param(
    [string]$Url = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip',
    [string]$Destination
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# 默认放在仓库根目录。注意别把 Join-Path 写在 param() 的默认值里——
# Windows PowerShell 5.1 在那个位置取不到 $PSScriptRoot。
if (-not $Destination) {
    $repoRoot = Split-Path -Parent $PSScriptRoot
    $Destination = Join-Path $repoRoot 'ffmpeg.exe'
}
$target = [System.IO.Path]::GetFullPath($Destination)

if (Test-Path $target) {
    Write-Host "ffmpeg.exe already present, skipping download: $target"
    exit 0
}

$parent = Split-Path -Parent $target
if ($parent -and -not (Test-Path $parent)) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
}

$work = Join-Path ([System.IO.Path]::GetTempPath()) ("ffmpeg-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work | Out-Null

try {
    $zip = Join-Path $work 'ffmpeg.zip'
    Write-Host "Downloading $Url"
    & curl.exe --fail --location --silent --show-error --output $zip $Url
    if ($LASTEXITCODE -ne 0) { throw "download failed (curl exit code $LASTEXITCODE)" }

    Expand-Archive -Path $zip -DestinationPath $work -Force

    # 只认 bin 目录下那个，避免误取到别的同名可执行文件
    $exe = Get-ChildItem -Path $work -Recurse -Filter 'ffmpeg.exe' |
        Where-Object { $_.Directory.Name -eq 'bin' } |
        Select-Object -First 1
    if (-not $exe) { throw 'no bin\ffmpeg.exe inside the archive' }

    Copy-Item -Path $exe.FullName -Destination $target -Force
    Write-Host "Placed: $target"
}
finally {
    Remove-Item -Path $work -Recurse -Force -ErrorAction SilentlyContinue
}
