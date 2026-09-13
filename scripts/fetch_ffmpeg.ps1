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

    注意：那个仓库是**滚动发布**——每几小时就出一个 autobuild，资产名里带构建
    哈希（如 ffmpeg-N-126537-g7523428c26-win64-lgpl.zip），名字每轮都变。
    所以这里不能写死文件名，得先查一下当前 release 里有什么。写死的话，
    上一次能下、下一次就 404。

    文件已经存在时直接跳过，方便反复调用。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/fetch_ffmpeg.ps1

.EXAMPLE
    # 换成自定义来源，跳过自动解析
    powershell -ExecutionPolicy Bypass -File scripts/fetch_ffmpeg.ps1 -Url https://example.com/ffmpeg.zip
#>
[CmdletBinding()]
param(
    [string]$Url,
    [string]$Destination
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$ReleaseApi = 'https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest'
# 只要 master 版的 LGPL 静态构建；带 -8.1 / -9.0 后缀的是分支版，不选
$AssetPattern = 'ffmpeg-*-win64-lgpl.zip'

function Resolve-LgplAssetUrl {
    Write-Host 'Looking up the current LGPL build...'

    $headers = @{ 'User-Agent' = 'TuneLift-build' }
    # 有 token 就用上，避免 CI 上撞到匿名调用的速率限制
    if ($env:GITHUB_TOKEN) {
        $headers['Authorization'] = "Bearer $($env:GITHUB_TOKEN)"
    }

    $release = Invoke-RestMethod -Uri $ReleaseApi -Headers $headers
    $asset = $release.assets |
        Where-Object { $_.name -like $AssetPattern } |
        Select-Object -First 1

    if (-not $asset) {
        throw "no asset matching '$AssetPattern' in release $($release.tag_name)"
    }
    Write-Host "  $($release.tag_name) -> $($asset.name)"
    return $asset.browser_download_url
}

function Get-SystemProxy {
    # curl.exe 不读 Windows 的系统代理设置（只认 http_proxy / https_proxy 环境变量），
    # 所以在开着系统代理的机器上会直连失败。这里读一下注册表，显式传给它。
    if ($env:HTTPS_PROXY -or $env:https_proxy -or $env:HTTP_PROXY -or $env:http_proxy) {
        return $null  # 环境变量已设，curl 自己会用
    }
    try {
        $cfg = Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction Stop
        if ($cfg.ProxyEnable -eq 1 -and $cfg.ProxyServer) {
            $server = $cfg.ProxyServer
            if ($server -notmatch '^[a-z]+://') { $server = "http://$server" }
            return $server
        }
    }
    catch { }
    return $null
}

# 默认放在仓库根目录。注意别把 Join-Path 写在 param() 的默认值里——
# Windows PowerShell 5.1 在那个位置取不到 $PSScriptRoot。
if (-not $Destination) {
    $Destination = Join-Path (Split-Path -Parent $PSScriptRoot) 'ffmpeg.exe'
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

if (-not $Url) {
    $Url = Resolve-LgplAssetUrl
}

$work = Join-Path ([System.IO.Path]::GetTempPath()) ("ffmpeg-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work | Out-Null

try {
    $zip = Join-Path $work 'ffmpeg.zip'
    Write-Host "Downloading $Url"

    $curlArgs = @('--fail', '--location', '--silent', '--show-error', '--output', $zip, $Url)
    $proxy = Get-SystemProxy
    if ($proxy) {
        Write-Host "  using system proxy $proxy"
        $curlArgs = @('--proxy', $proxy) + $curlArgs
    }

    & curl.exe @curlArgs
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
