<#
  Acid Zero - laptop clipboard sync.

  Two-way clipboard sync between this Windows PC and the Acid Zero Pi's Terminal
  app, over your LAN. Copy a command here (Ctrl+C) -> it lands on the Pi -> open
  Terminal on the device, tap PASTE, review it, tap RUN. Text the Pi copies out
  (Terminal's COPY button) flows back to this PC's clipboard.

  One-time: get the token from the Pi ->  cat /etc/acid-clip.token
  Run (Windows CMD):
    powershell -ExecutionPolicy Bypass -File tools\acid-clip-sync.ps1 -Token PASTE_TOKEN_HERE
  Optional: -Pi 192.168.1.5 -Port 8899   (defaults shown)

  Own-devices / own-lab use only.
#>
param(
    [string]$Pi    = "192.168.1.5",
    [int]   $Port  = 8899,
    [string]$Token = $env:ACID_CLIP_TOKEN
)

if ([string]::IsNullOrWhiteSpace($Token)) {
    Write-Error "No token. Pass -Token <token>  (get it once from the Pi: cat /etc/acid-clip.token)"
    exit 1
}

$base = "http://{0}:{1}/clip" -f $Pi, $Port
$hdr  = @{ "X-Acid-Token" = $Token }
$lastLocal  = $null
$lastRemote = $null

Write-Host ("Acid Zero clipboard sync  ->  {0}:{1}   (Ctrl+C to stop)" -f $Pi, $Port) -ForegroundColor Cyan

while ($true) {
    try {
        # $null = empty OR non-text (image/file) clipboard. Treat empty as "no update"
        # in BOTH directions so we never clobber the peer with a "".
        $local = Get-Clipboard -Raw -ErrorAction SilentlyContinue
        if ($null -eq $local) { $local = "" }

        if (($local -ne $lastLocal) -and -not [string]::IsNullOrEmpty($local)) {
            # local clipboard changed to real text -> push to the Pi
            $bytes = [System.Text.Encoding]::UTF8.GetBytes($local)
            Invoke-RestMethod -Uri $base -Method Post -Headers $hdr `
                -Body $bytes -ContentType "text/plain; charset=utf-8" -TimeoutSec 4 | Out-Null
            $lastLocal  = $local
            $lastRemote = $local        # Pi now holds this; don't pull it straight back
        }
        else {
            $lastLocal = $local          # remember current (incl empty) so we don't retry it
            # local unchanged/empty -> see if the Pi copied something out
            $r = Invoke-RestMethod -Uri $base -Method Get -Headers $hdr -TimeoutSec 4
            if ($null -ne $r -and -not [string]::IsNullOrEmpty($r.text) -and $r.text -ne $lastRemote) {
                if ($r.text -ne $local) { Set-Clipboard -Value $r.text }
                $lastRemote = $r.text
                $lastLocal  = $r.text    # avoid bouncing it back as a "local change"
            }
        }
    }
    catch {
        Start-Sleep -Milliseconds 1500   # Pi asleep / Wi-Fi blip -> back off and retry
    }
    Start-Sleep -Milliseconds 800
}
