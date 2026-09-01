Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class NativeMethods {
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern IntPtr SendMessage(IntPtr hWnd, int msg, IntPtr wParam, string lParam);
    public const int EM_SETCUEBANNER = 0x1501;
    public static void SetPlaceholder(System.Windows.Forms.Control ctrl, string text) {
        SendMessage(ctrl.Handle, EM_SETCUEBANNER, (IntPtr)1, text);
    }
}
"@

$YT_DLP = "C:\ERAR\yt-dlp\dist\yt-dlp.exe"

# ── Colour palette ────────────────────────────────────────────────────────────
$bg0  = [System.Drawing.Color]::FromArgb(18,  18,  18)
$bg1  = [System.Drawing.Color]::FromArgb(28,  28,  28)
$bg2  = [System.Drawing.Color]::FromArgb(40,  40,  40)
$bg3  = [System.Drawing.Color]::FromArgb(55,  55,  55)
$fg0  = [System.Drawing.Color]::White
$fg1  = [System.Drawing.Color]::FromArgb(170, 170, 170)
$fg2  = [System.Drawing.Color]::FromArgb(110, 110, 110)
$red  = [System.Drawing.Color]::FromArgb(220, 38,  38)
$blue = [System.Drawing.Color]::FromArgb(100, 160, 255)

# ── Format definitions ─────────────────────────────────────────────────────────
# Video: resolution options per format type
$videoQualities = [ordered]@{
    "Best available"  = ""
    "4K (2160p)"      = "[height<=2160]"
    "1440p"           = "[height<=1440]"
    "1080p"           = "[height<=1080]"
    "720p"            = "[height<=720]"
    "480p"            = "[height<=480]"
    "360p"            = "[height<=360]"
}
# Audio: bitrate options
$audioQualities = [ordered]@{
    "Best (VBR)"      = "0"
    "320 Kbps"        = "320K"
    "256 Kbps"        = "256K"
    "192 Kbps"        = "192K"
    "128 Kbps"        = "128K"
}

# Format categories: "video" or "audio"
$formatTypes = [ordered]@{
    "Best Quality (auto)" = "video"
    "MP4"                 = "video"
    "MKV"                 = "video"
    "WebM"                = "video"
    "MP3"                 = "audio"
    "M4A"                 = "audio"
    "AAC"                 = "audio"
    "FLAC"                = "audio"
    "WAV"                 = "audio"
    "OPUS"                = "audio"
    "OGG"                 = "audio"
}

function Build-Args($fmtKey, $qualKey, $dest, $url, $settings) {
    $type = $formatTypes[$fmtKey]
    $args = @()

    if ($type -eq "audio") {
        $fmt   = "bestaudio"
        $brate = $audioQualities[$qualKey]
        $afmt  = switch ($fmtKey) {
            "MP3"  { "mp3"    }
            "M4A"  { "m4a"    }
            "AAC"  { "aac"    }
            "FLAC" { "flac"   }
            "WAV"  { "wav"    }
            "OPUS" { "opus"   }
            "OGG"  { "vorbis" }
            default { "mp3"   }
        }
        $args += "-f", $fmt, "-x", "--audio-format", $afmt, "--audio-quality", $brate
    } else {
        $q = $videoQualities[$qualKey]
        switch ($fmtKey) {
            "Best Quality (auto)" {
                $args += "-f", "bestvideo+bestaudio/best"
            }
            "MP4" {
                if ($q) {
                    $args += "-f", "bestvideo$q[ext=mp4]+bestaudio[ext=m4a]/bestvideo$q+bestaudio/best$q"
                } else {
                    $args += "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
                }
                $args += "--merge-output-format", "mp4"
            }
            "MKV" {
                if ($q) {
                    $args += "-f", "bestvideo$q+bestaudio/best$q"
                } else {
                    $args += "-f", "bestvideo+bestaudio/best"
                }
                $args += "--merge-output-format", "mkv"
            }
            "WebM" {
                if ($q) {
                    $args += "-f", "bestvideo$q[ext=webm]+bestaudio[ext=webm]/best$q"
                } else {
                    $args += "-f", "bestvideo[ext=webm]+bestaudio[ext=webm]/best"
                }
            }
            default {
                $args += "-f", "bestvideo+bestaudio/best"
            }
        }
    }

    # ── Post-processing settings ──────────────────────────────────────────────
    if ($settings.EmbedThumbnail)  { $args += "--embed-thumbnail" }
    if ($settings.EmbedMetadata)   { $args += "--embed-metadata" }
    if ($settings.EmbedChapters)   { $args += "--embed-chapters" }
    if ($settings.SponsorBlock)    { $args += "--sponsorblock-remove", "all" }

    if ($settings.RemuxTo -and $settings.RemuxTo -ne "None") {
        $args += "--remux-video", $settings.RemuxTo.ToLower()
    }

    # ── Subtitle settings ─────────────────────────────────────────────────────
    if ($settings.WriteSubs) {
        $args += "--write-subs"
        if ($settings.SubLangs) { $args += "--sub-langs", $settings.SubLangs }
    }
    if ($settings.WriteAutoSubs) { $args += "--write-auto-subs" }

    # ── Network settings ──────────────────────────────────────────────────────
    if ($settings.RateLimit) { $args += "--limit-rate", $settings.RateLimit }
    if ($settings.ConcurrentFrags -gt 1) { $args += "-N", "$($settings.ConcurrentFrags)" }
    if ($settings.Cookies -and $settings.Cookies -ne "None") {
        $args += "--cookies-from-browser", $settings.Cookies.ToLower()
    }

    # ── Playlist settings ─────────────────────────────────────────────────────
    if ($settings.PlaylistMode -eq "single") { $args += "--no-playlist" }
    if ($settings.PlaylistMode -eq "full")   { $args += "--yes-playlist" }

    $outTmpl = Join-Path $dest "%(title)s.%(ext)s"
    $args += "-o", $outTmpl, $url
    return $args
}

# ── Main form ──────────────────────────────────────────────────────────────────
$form = New-Object System.Windows.Forms.Form
$form.Text            = "YT-DLP Downloader"
$form.ClientSize      = New-Object System.Drawing.Size(660, 620)
$form.StartPosition   = "CenterScreen"
$form.BackColor       = $bg0
$form.ForeColor       = $fg0
$form.Font            = New-Object System.Drawing.Font("Segoe UI", 9.5)
$form.FormBorderStyle = "FixedSingle"
$form.MaximizeBox     = $false

# ── Tab control ────────────────────────────────────────────────────────────────
$tabs = New-Object System.Windows.Forms.TabControl
$tabs.Location  = New-Object System.Drawing.Point(0, 0)
$tabs.Size      = New-Object System.Drawing.Size(660, 620)
$tabs.BackColor = $bg0
$tabs.ForeColor = $fg0
$tabs.Font      = New-Object System.Drawing.Font("Segoe UI", 9.5)
$form.Controls.Add($tabs)

$tabDownload = New-Object System.Windows.Forms.TabPage
$tabDownload.Text      = "  Download  "
$tabDownload.BackColor = $bg0
$tabDownload.ForeColor = $fg0
$tabs.TabPages.Add($tabDownload)

$tabSettings = New-Object System.Windows.Forms.TabPage
$tabSettings.Text      = "  Settings  "
$tabSettings.BackColor = $bg0
$tabSettings.ForeColor = $fg0
$tabs.TabPages.Add($tabSettings)

# ══════════════════════════════════════════════════════════════════════════════
# DOWNLOAD TAB
# ══════════════════════════════════════════════════════════════════════════════
function New-Label($parent, $text, $x, $y) {
    $l = New-Object System.Windows.Forms.Label
    $l.Text      = $text
    $l.Location  = New-Object System.Drawing.Point($x, $y)
    $l.AutoSize  = $true
    $l.ForeColor = $fg1
    $parent.Controls.Add($l)
    return $l
}

function New-TextBox($parent, $x, $y, $w, $placeholder) {
    $t = New-Object System.Windows.Forms.TextBox
    $t.Location        = New-Object System.Drawing.Point($x, $y)
    $t.Size            = New-Object System.Drawing.Size($w, 28)
    $t.BackColor       = $bg2
    $t.ForeColor       = $fg0
    $t.BorderStyle     = "FixedSingle"
    if ($placeholder) { $t.Add_HandleCreated({ [NativeMethods]::SetPlaceholder($t, $placeholder) }) }
    $parent.Controls.Add($t)
    return $t
}

function New-Combo($parent, $x, $y, $w, $items) {
    $c = New-Object System.Windows.Forms.ComboBox
    $c.Location      = New-Object System.Drawing.Point($x, $y)
    $c.Size          = New-Object System.Drawing.Size($w, 28)
    $c.BackColor     = $bg2
    $c.ForeColor     = $fg0
    $c.FlatStyle     = "Flat"
    $c.DropDownStyle = "DropDownList"
    foreach ($i in $items) { [void]$c.Items.Add($i) }
    $c.SelectedIndex = 0
    $parent.Controls.Add($c)
    return $c
}

function New-Check($parent, $text, $x, $y) {
    $cb = New-Object System.Windows.Forms.CheckBox
    $cb.Text      = $text
    $cb.Location  = New-Object System.Drawing.Point($x, $y)
    $cb.AutoSize  = $true
    $cb.ForeColor = $fg1
    $cb.FlatStyle = "Flat"
    $parent.Controls.Add($cb)
    return $cb
}

function New-GroupBox($parent, $text, $x, $y, $w, $h) {
    $g = New-Object System.Windows.Forms.GroupBox
    $g.Text      = $text
    $g.Location  = New-Object System.Drawing.Point($x, $y)
    $g.Size      = New-Object System.Drawing.Size($w, $h)
    $g.ForeColor = $fg2
    $g.FlatStyle = "Flat"
    $parent.Controls.Add($g)
    return $g
}

# ── URL ───────────────────────────────────────────────────────────────────────
New-Label $tabDownload "YouTube / Video URL" 16 16 | Out-Null
$txtUrl = New-TextBox $tabDownload 16 38 618 "Paste a link here..."

# ── Format + Quality ──────────────────────────────────────────────────────────
New-Label $tabDownload "Format" 16 82 | Out-Null
New-Label $tabDownload "Quality / Resolution" 320 82 | Out-Null

$cboFormat = New-Combo $tabDownload 16 102 296 $formatTypes.Keys
$cboQuality = New-Combo $tabDownload 320 102 314 $videoQualities.Keys

# When format changes, swap quality options between video res and audio bitrate
$cboFormat.Add_SelectedIndexChanged({
    $fmtKey = $cboFormat.SelectedItem
    $type = $formatTypes[$fmtKey]
    $cboQuality.Items.Clear()
    if ($type -eq "audio") {
        foreach ($k in $audioQualities.Keys) { [void]$cboQuality.Items.Add($k) }
    } else {
        foreach ($k in $videoQualities.Keys) { [void]$cboQuality.Items.Add($k) }
    }
    $cboQuality.SelectedIndex = 0
})

# ── Destination ───────────────────────────────────────────────────────────────
New-Label $tabDownload "Destination Folder" 16 148 | Out-Null
$txtDest = New-TextBox $tabDownload 16 168 522 $null
$txtDest.Text = [Environment]::GetFolderPath("MyVideos")

$btnBrowse = New-Object System.Windows.Forms.Button
$btnBrowse.Location                   = New-Object System.Drawing.Point(546, 167)
$btnBrowse.Size                       = New-Object System.Drawing.Size(88, 30)
$btnBrowse.Text                       = "Browse..."
$btnBrowse.BackColor                  = $bg2
$btnBrowse.ForeColor                  = $fg0
$btnBrowse.FlatStyle                  = "Flat"
$btnBrowse.FlatAppearance.BorderColor = $bg3
$btnBrowse.Cursor                     = "Hand"
$tabDownload.Controls.Add($btnBrowse)

$btnBrowse.Add_Click({
    $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
    $dlg.SelectedPath = $txtDest.Text
    if ($dlg.ShowDialog() -eq "OK") { $txtDest.Text = $dlg.SelectedPath }
})

# ── Download button ────────────────────────────────────────────────────────────
$btnDownload = New-Object System.Windows.Forms.Button
$btnDownload.Location                  = New-Object System.Drawing.Point(16, 212)
$btnDownload.Size                      = New-Object System.Drawing.Size(618, 44)
$btnDownload.Text                      = "Download"
$btnDownload.BackColor                 = $red
$btnDownload.ForeColor                 = $fg0
$btnDownload.FlatStyle                 = "Flat"
$btnDownload.FlatAppearance.BorderSize = 0
$btnDownload.Font                      = New-Object System.Drawing.Font("Segoe UI Semibold", 11)
$btnDownload.Cursor                    = "Hand"
$tabDownload.Controls.Add($btnDownload)

# ── Log ───────────────────────────────────────────────────────────────────────
New-Label $tabDownload "Output Log" 16 270 | Out-Null

$txtLog = New-Object System.Windows.Forms.RichTextBox
$txtLog.Location    = New-Object System.Drawing.Point(16, 290)
$txtLog.Size        = New-Object System.Drawing.Size(618, 240)
$txtLog.BackColor   = [System.Drawing.Color]::FromArgb(10,10,10)
$txtLog.ForeColor   = [System.Drawing.Color]::FromArgb(180,255,180)
$txtLog.ReadOnly    = $true
$txtLog.BorderStyle = "None"
$txtLog.ScrollBars  = "Vertical"
try   { $txtLog.Font = New-Object System.Drawing.Font("Cascadia Code", 8.5) }
catch { $txtLog.Font = New-Object System.Drawing.Font("Consolas", 9) }
$tabDownload.Controls.Add($txtLog)

$btnClear = New-Object System.Windows.Forms.Button
$btnClear.Location                   = New-Object System.Drawing.Point(16, 537)
$btnClear.Size                       = New-Object System.Drawing.Size(618, 24)
$btnClear.Text                       = "Clear log"
$btnClear.BackColor                  = $bg1
$btnClear.ForeColor                  = $fg2
$btnClear.FlatStyle                  = "Flat"
$btnClear.FlatAppearance.BorderColor = $bg2
$btnClear.Font                       = New-Object System.Drawing.Font("Segoe UI", 8)
$btnClear.Cursor                     = "Hand"
$tabDownload.Controls.Add($btnClear)
$btnClear.Add_Click({ $txtLog.Clear() })

# ══════════════════════════════════════════════════════════════════════════════
# SETTINGS TAB
# ══════════════════════════════════════════════════════════════════════════════

# ── Post-Processing group ─────────────────────────────────────────────────────
$grpPost = New-GroupBox $tabSettings "Post-Processing" 10 10 630 115
$chkThumb    = New-Check $grpPost "Embed thumbnail as cover art"     12 22
$chkMeta     = New-Check $grpPost "Embed metadata (title, artist...)" 12 46
$chkChapters = New-Check $grpPost "Embed chapter markers"            12 70
$chkSponsor  = New-Check $grpPost "SponsorBlock: remove sponsored segments" 300 22

$lRemux = New-Object System.Windows.Forms.Label
$lRemux.Text = "Remux to:"; $lRemux.Location = New-Object System.Drawing.Point(300, 50)
$lRemux.AutoSize = $true; $lRemux.ForeColor = $fg1
$grpPost.Controls.Add($lRemux)

$cboRemux = New-Combo $grpPost 365 46 130 @("None","mp4","mkv","mov","webm","avi","flv")

$lRecode = New-Object System.Windows.Forms.Label
$lRecode.Text = "Re-encode to:"; $lRecode.Location = New-Object System.Drawing.Point(300, 78)
$lRecode.AutoSize = $true; $lRecode.ForeColor = $fg1
$grpPost.Controls.Add($lRecode)

$cboRecode = New-Combo $grpPost 393 74 102 @("None","mp4","mkv","mov","webm","mp3","m4a","wav")

# ── Subtitles group ────────────────────────────────────────────────────────────
$grpSubs = New-GroupBox $tabSettings "Subtitles" 10 135 630 88
$chkSubs     = New-Check $grpSubs "Download subtitles" 12 22
$chkAutoSubs = New-Check $grpSubs "Include auto-generated subtitles" 12 46

$lSubLang = New-Object System.Windows.Forms.Label
$lSubLang.Text = "Languages (comma-separated, e.g. en,ja):"
$lSubLang.Location = New-Object System.Drawing.Point(280, 24); $lSubLang.AutoSize = $true
$lSubLang.ForeColor = $fg1; $grpSubs.Controls.Add($lSubLang)

$txtSubLangs = New-TextBox $grpSubs 280 44 200 "en"
$txtSubLangs.Text = "en"

# ── Network group ──────────────────────────────────────────────────────────────
$grpNet = New-GroupBox $tabSettings "Network" 10 233 630 112

$lRate = New-Object System.Windows.Forms.Label
$lRate.Text = "Rate limit (e.g. 5M, 500K, blank=off):"; $lRate.Location = New-Object System.Drawing.Point(12, 24)
$lRate.AutoSize = $true; $lRate.ForeColor = $fg1; $grpNet.Controls.Add($lRate)
$txtRate = New-TextBox $grpNet 12 44 150 "e.g. 5M"

$lFrags = New-Object System.Windows.Forms.Label
$lFrags.Text = "Concurrent fragments:"; $lFrags.Location = New-Object System.Drawing.Point(180, 24)
$lFrags.AutoSize = $true; $lFrags.ForeColor = $fg1; $grpNet.Controls.Add($lFrags)
$numFrags = New-Object System.Windows.Forms.NumericUpDown
$numFrags.Location = New-Object System.Drawing.Point(180, 44); $numFrags.Size = New-Object System.Drawing.Size(72, 26)
$numFrags.Minimum = 1; $numFrags.Maximum = 32; $numFrags.Value = 1
$numFrags.BackColor = $bg2; $numFrags.ForeColor = $fg0; $numFrags.BorderStyle = "FixedSingle"
$grpNet.Controls.Add($numFrags)

$lCookies = New-Object System.Windows.Forms.Label
$lCookies.Text = "Cookies from browser:"; $lCookies.Location = New-Object System.Drawing.Point(270, 24)
$lCookies.AutoSize = $true; $lCookies.ForeColor = $fg1; $grpNet.Controls.Add($lCookies)
$cboCookies = New-Combo $grpNet 270 44 180 @("None","chrome","firefox","edge","brave","opera","safari","vivaldi","chromium")

$lRetries = New-Object System.Windows.Forms.Label
$lRetries.Text = "Retries:"; $lRetries.Location = New-Object System.Drawing.Point(468, 24)
$lRetries.AutoSize = $true; $lRetries.ForeColor = $fg1; $grpNet.Controls.Add($lRetries)
$numRetries = New-Object System.Windows.Forms.NumericUpDown
$numRetries.Location = New-Object System.Drawing.Point(468, 44); $numRetries.Size = New-Object System.Drawing.Size(60, 26)
$numRetries.Minimum = 1; $numRetries.Maximum = 50; $numRetries.Value = 10
$numRetries.BackColor = $bg2; $numRetries.ForeColor = $fg0; $numRetries.BorderStyle = "FixedSingle"
$grpNet.Controls.Add($numRetries)

$lProxy = New-Object System.Windows.Forms.Label
$lProxy.Text = "Proxy (e.g. socks5://127.0.0.1:1080):"; $lProxy.Location = New-Object System.Drawing.Point(12, 78)
$lProxy.AutoSize = $true; $lProxy.ForeColor = $fg1; $grpNet.Controls.Add($lProxy)
$txtProxy = New-TextBox $grpNet 240 74 290 "leave blank to skip"

# ── Playlist group ─────────────────────────────────────────────────────────────
$grpPlaylist = New-GroupBox $tabSettings "Playlist Handling" 10 355 630 64
$rdoAuto   = New-Object System.Windows.Forms.RadioButton
$rdoSingle = New-Object System.Windows.Forms.RadioButton
$rdoFull   = New-Object System.Windows.Forms.RadioButton
foreach ($r in @($rdoAuto, $rdoSingle, $rdoFull)) {
    $r.ForeColor = $fg1; $r.FlatStyle = "Flat"; $r.AutoSize = $true
    $grpPlaylist.Controls.Add($r)
}
$rdoAuto.Text   = "Auto (let yt-dlp decide)"; $rdoAuto.Location   = New-Object System.Drawing.Point(12,  24); $rdoAuto.Checked = $true
$rdoSingle.Text = "Single video only";         $rdoSingle.Location = New-Object System.Drawing.Point(210, 24)
$rdoFull.Text   = "Always download full playlist"; $rdoFull.Location = New-Object System.Drawing.Point(380, 24)

# ── Output template group ──────────────────────────────────────────────────────
$grpOut = New-GroupBox $tabSettings "Output Filename Template" 10 429 630 64
$lOutTmpl = New-Object System.Windows.Forms.Label
$lOutTmpl.Text = "Template (yt-dlp format, %(title)s.%(ext)s = default):"
$lOutTmpl.Location = New-Object System.Drawing.Point(12, 20); $lOutTmpl.AutoSize = $true
$lOutTmpl.ForeColor = $fg1; $grpOut.Controls.Add($lOutTmpl)
$txtOutTmpl = New-TextBox $grpOut 12 40 606 $null
$txtOutTmpl.Text = "%(title)s.%(ext)s"

# ── Extra args ─────────────────────────────────────────────────────────────────
$grpExtra = New-GroupBox $tabSettings "Extra yt-dlp Arguments" 10 503 630 56
$lExtra = New-Object System.Windows.Forms.Label
$lExtra.Text = "Any additional flags appended verbatim:"; $lExtra.Location = New-Object System.Drawing.Point(12, 18)
$lExtra.AutoSize = $true; $lExtra.ForeColor = $fg1; $grpExtra.Controls.Add($lExtra)
$txtExtra = New-TextBox $grpExtra 12 36 606 "e.g. --no-mtime --write-info-json"

# ══════════════════════════════════════════════════════════════════════════════
# LOG HELPERS
# ══════════════════════════════════════════════════════════════════════════════
function Append-Log {
    param($text, [System.Drawing.Color]$color = [System.Drawing.Color]::FromArgb(210,210,210))
    $txtLog.SelectionStart  = $txtLog.TextLength
    $txtLog.SelectionLength = 0
    $txtLog.SelectionColor  = $color
    $txtLog.AppendText("$text`n")
    $txtLog.ScrollToCaret()
}

# ══════════════════════════════════════════════════════════════════════════════
# DOWNLOAD LOGIC
# ══════════════════════════════════════════════════════════════════════════════
$script:proc  = $null
$script:timer = $null
$script:queue = $null

$btnDownload.Add_Click({
    $url    = $txtUrl.Text.Trim()
    $dest   = $txtDest.Text.Trim()
    $fmtKey = $cboFormat.SelectedItem
    $qualKey = $cboQuality.SelectedItem

    if ([string]::IsNullOrEmpty($url)) {
        [System.Windows.Forms.MessageBox]::Show("Please paste a URL first.", "Missing URL", "OK", "Warning"); return
    }
    if (-not (Test-Path $dest)) {
        [System.Windows.Forms.MessageBox]::Show("Destination folder does not exist.", "Bad path", "OK", "Warning"); return
    }
    if (-not (Test-Path $YT_DLP)) {
        [System.Windows.Forms.MessageBox]::Show("yt-dlp.exe not found at:`n$YT_DLP", "Not found", "OK", "Error"); return
    }

    $playlistMode = if ($rdoSingle.Checked) { "single" } elseif ($rdoFull.Checked) { "full" } else { "auto" }

    $settings = [PSCustomObject]@{
        EmbedThumbnail   = $chkThumb.Checked
        EmbedMetadata    = $chkMeta.Checked
        EmbedChapters    = $chkChapters.Checked
        SponsorBlock     = $chkSponsor.Checked
        RemuxTo          = $cboRemux.SelectedItem
        RecodeTo         = $cboRecode.SelectedItem
        WriteSubs        = $chkSubs.Checked
        WriteAutoSubs    = $chkAutoSubs.Checked
        SubLangs         = $txtSubLangs.Text.Trim()
        RateLimit        = $txtRate.Text.Trim()
        ConcurrentFrags  = [int]$numFrags.Value
        Cookies          = $cboCookies.SelectedItem
        Retries          = [int]$numRetries.Value
        Proxy            = $txtProxy.Text.Trim()
        PlaylistMode     = $playlistMode
        OutTemplate      = $txtOutTmpl.Text.Trim()
        ExtraArgs        = $txtExtra.Text.Trim()
    }

    $allArgs = Build-Args $fmtKey $qualKey $dest $url $settings

    # Apply re-encode (separate from remux)
    if ($settings.RecodeTo -and $settings.RecodeTo -ne "None") {
        $allArgs = @("--recode-video", $settings.RecodeTo.ToLower()) + $allArgs
    }

    # Apply retries
    $allArgs += "--retries", "$($settings.Retries)"

    # Apply proxy
    if ($settings.Proxy) { $allArgs += "--proxy", $settings.Proxy }

    # Override output template if custom
    if ($settings.OutTemplate -and $settings.OutTemplate -ne "%(title)s.%(ext)s") {
        # replace the -o arg we already added
        $oIdx = [Array]::IndexOf($allArgs, "-o")
        if ($oIdx -ge 0) { $allArgs[$oIdx + 1] = (Join-Path $dest $settings.OutTemplate) }
    }

    # Extra raw args
    if ($settings.ExtraArgs) {
        $allArgs += $settings.ExtraArgs -split '\s+(?=(?:[^"]*"[^"]*")*[^"]*$)'
    }

    # Switch to download tab to show log
    $tabs.SelectedTab = $tabDownload

    $btnDownload.Enabled = $false
    $btnDownload.Text    = "Downloading..."
    Append-Log "Starting: $url" $blue
    Append-Log "  Format  : $fmtKey | $qualKey" $fg2
    Append-Log "  Dest    : $dest" $fg2
    Append-Log "" ([System.Drawing.Color]::White)

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName               = $YT_DLP
    $psi.Arguments              = ($allArgs | ForEach-Object {
        if ($_ -match '[\s\[\]]') { "`"$_`"" } else { $_ }
    }) -join ' '
    $psi.UseShellExecute        = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError  = $true
    $psi.CreateNoWindow         = $true

    $script:proc  = New-Object System.Diagnostics.Process
    $script:proc.StartInfo = $psi
    $script:queue = [System.Collections.Concurrent.ConcurrentQueue[string]]::new()
    $q = $script:queue

    $script:proc.add_OutputDataReceived({ param($s,$e); if ($null -ne $e.Data) { $q.Enqueue($e.Data) } })
    $script:proc.add_ErrorDataReceived({  param($s,$e); if ($null -ne $e.Data) { $q.Enqueue("ERR: " + $e.Data) } })

    [void]$script:proc.Start()
    $script:proc.BeginOutputReadLine()
    $script:proc.BeginErrorReadLine()

    if ($script:timer) { $script:timer.Stop(); $script:timer.Dispose() }
    $script:timer = New-Object System.Windows.Forms.Timer
    $script:timer.Interval = 200
    $script:timer.Add_Tick({
        $line = $null
        while ($script:queue.TryDequeue([ref]$line)) {
            $col = if     ($line -match "^ERR:|ERROR")       { [System.Drawing.Color]::FromArgb(255,100,100) }
                   elseif ($line -match "\[download\]")       { [System.Drawing.Color]::FromArgb(100,220,100) }
                   elseif ($line -match "\[info\]|\[youtube\]|\[generic\]") { $blue }
                   else { [System.Drawing.Color]::FromArgb(210,210,210) }
            Append-Log $line $col
        }
        if ($script:proc -and $script:proc.HasExited) {
            $line2 = $null
            while ($script:queue.TryDequeue([ref]$line2)) { Append-Log $line2 ([System.Drawing.Color]::FromArgb(210,210,210)) }
            $script:timer.Stop()
            $ec = $script:proc.ExitCode
            $script:proc.Dispose(); $script:proc = $null
            if ($ec -eq 0) {
                Append-Log "Done - download complete." ([System.Drawing.Color]::FromArgb(80,220,80))
            } else {
                Append-Log "Failed - exit code $ec." ([System.Drawing.Color]::FromArgb(255,80,80))
            }
            Append-Log "" ([System.Drawing.Color]::White)
            $btnDownload.Enabled = $true
            $btnDownload.Text    = "Download"
        }
    })
    $script:timer.Start()
})

$form.Add_FormClosing({
    if ($script:timer) { $script:timer.Stop(); $script:timer.Dispose() }
    if ($script:proc -and -not $script:proc.HasExited) { $script:proc.Kill() }
})

[void]$form.ShowDialog()
