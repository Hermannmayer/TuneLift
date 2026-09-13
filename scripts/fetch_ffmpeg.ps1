<#
.SYNOPSIS
    把 ffmpeg.exe 下载到仓库根目录。

.DESCRIPTION
    ffmpeg 体积太大，不适合进版本库，所以 build.bat 需要它先在位。

    默认取 BtbN/FFmpeg-Builds 的 **LGPL** 变体。这一点是刻意的：
    gyan.dev 的构建全部是 GPLv3（页面原话 "All builds are ... licensed as GPLv3"），
    而 GPLv3 要求随包提供对应源码；LGPLv3 只需附许可证全文并保持可替换，
    对一个独立调用的 exe 来说负担小得多。

    LGPL 变体不含 --enable-gpl，因此没有 libx264/libx265 这些 GPL-only 组件。
    本项目只用音频解码 + MP3 编码（libmp3lame，同样是 LGPL），用不到它们。

    文件已经存在时直接跳过，方便反复调用。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/fetch_ffmpeg.ps1

.EXAMPLE
    # 换成自定义来源
    powershell -ExecutionPolicy Bypass -File scripts/fetch_ffmpeg.ps1 -Url https://example.com/ffmpeg.zip
#>
[CmdletBinding()]
param(
    [string]$Url = 'https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-lgpl.zip',
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
