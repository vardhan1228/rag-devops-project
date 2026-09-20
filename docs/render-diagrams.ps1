<#
.SYNOPSIS
  Renders every docs/diagrams/*.mmd file to PNG and SVG.

.DESCRIPTION
  Uses mermaid-cli through npx. mermaid-cli drives a headless Chromium via
  Puppeteer, and Puppeteer ships without a browser, so this script points it at
  an already installed Chrome or Edge instead of downloading one.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File docs/render-diagrams.ps1
#>

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$diagramDir = Join-Path $repoRoot 'docs\diagrams'

# Prefer Chrome, fall back to Edge, which is present on every Windows install.
$browserCandidates = @(
  "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
  "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
  "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
  "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
)

$browser = $browserCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $browser) {
  throw "No Chrome or Edge found. Install one, or run: npx puppeteer browsers install chrome"
}
Write-Host "Browser: $browser"

# Puppeteer config consumed by mermaid-cli via -p.
$puppeteerConfig = Join-Path $env:TEMP 'mermaid-puppeteer.json'
@{ executablePath = $browser; args = @('--no-sandbox') } |
  ConvertTo-Json -Compress |
  Set-Content -Path $puppeteerConfig -Encoding ascii

$sources = Get-ChildItem -Path $diagramDir -Filter '*.mmd' | Sort-Object Name
if (-not $sources) { throw "No .mmd files in $diagramDir" }

foreach ($src in $sources) {
  foreach ($format in @('png', 'svg')) {
    $out = Join-Path $diagramDir ("$($src.BaseName).$format")

    # scale 2 gives a readable PNG on high density displays.
    npx --yes @mermaid-js/mermaid-cli@11.4.2 `
      -i $src.FullName `
      -o $out `
      -p $puppeteerConfig `
      -t neutral `
      -b white `
      --scale 2 2>&1 | Where-Object { $_ -notmatch '^Generating' }

    if (-not (Test-Path $out)) { throw "Failed to render $($src.Name) to $format" }
    Write-Host ("  {0,-46} {1,8:N0} bytes" -f (Split-Path $out -Leaf), (Get-Item $out).Length)
  }
}

Remove-Item $puppeteerConfig -ErrorAction SilentlyContinue
Write-Host "`nDone. $($sources.Count) diagram(s) rendered to PNG and SVG in docs/diagrams."
