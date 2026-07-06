Add-Type -AssemblyName System.Windows.Forms, System.Drawing

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Runner = Join-Path $PSScriptRoot "run.ps1"
$script:Process = $null

$form = New-Object System.Windows.Forms.Form
$form.Text = "ADB Device Manager Build"
$form.Size = New-Object System.Drawing.Size(760, 500)
$form.StartPosition = "CenterScreen"
$form.MinimumSize = New-Object System.Drawing.Size(680, 420)

$modeBox = New-Object System.Windows.Forms.GroupBox
$modeBox.Text = "Python mode"
$modeBox.Location = New-Object System.Drawing.Point(12, 10)
$modeBox.Size = New-Object System.Drawing.Size(260, 58)
$form.Controls.Add($modeBox)

$venvRadio = New-Object System.Windows.Forms.RadioButton
$venvRadio.Text = "Managed .venv"
$venvRadio.Checked = $true
$venvRadio.Location = New-Object System.Drawing.Point(12, 24)
$venvRadio.AutoSize = $true
$modeBox.Controls.Add($venvRadio)

$systemRadio = New-Object System.Windows.Forms.RadioButton
$systemRadio.Text = "Active/system Python"
$systemRadio.Location = New-Object System.Drawing.Point(130, 24)
$systemRadio.AutoSize = $true
$modeBox.Controls.Add($systemRadio)

$status = New-Object System.Windows.Forms.Label
$status.Text = "Idle"
$status.Location = New-Object System.Drawing.Point(290, 32)
$status.Size = New-Object System.Drawing.Size(440, 24)
$form.Controls.Add($status)

$buttons = New-Object System.Windows.Forms.FlowLayoutPanel
$buttons.Location = New-Object System.Drawing.Point(12, 78)
$buttons.Size = New-Object System.Drawing.Size(720, 74)
$buttons.Anchor = "Top,Left,Right"
$buttons.WrapContents = $true
$form.Controls.Add($buttons)

$output = New-Object System.Windows.Forms.TextBox
$output.Multiline = $true
$output.ScrollBars = "Both"
$output.ReadOnly = $true
$output.WordWrap = $false
$output.Font = New-Object System.Drawing.Font("Consolas", 9)
$output.Location = New-Object System.Drawing.Point(12, 160)
$output.Size = New-Object System.Drawing.Size(720, 250)
$output.Anchor = "Top,Bottom,Left,Right"
$form.Controls.Add($output)

$bottom = New-Object System.Windows.Forms.FlowLayoutPanel
$bottom.Location = New-Object System.Drawing.Point(12, 420)
$bottom.Size = New-Object System.Drawing.Size(720, 34)
$bottom.Anchor = "Bottom,Left,Right"
$form.Controls.Add($bottom)

function Append-Output {
    param([string]$Text)
    if ($null -eq $Text) { return }
    $form.BeginInvoke([action]{
        $output.AppendText($Text + [Environment]::NewLine)
        $output.SelectionStart = $output.TextLength
        $output.ScrollToCaret()
    }) | Out-Null
}

function Set-Running {
    param([bool]$Running, [string]$Text)
    $form.BeginInvoke([action]{
        foreach ($control in $buttons.Controls) { $control.Enabled = -not $Running }
        $stopBtn.Enabled = $Running
        $status.Text = $Text
    }) | Out-Null
}

function Start-Action {
    param([string]$Action, [bool]$DesktopDeps = $false)
    if ($script:Process -ne $null -and -not $script:Process.HasExited) {
        Append-Output "Another action is already running."
        return
    }

    $args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$Runner`"", "-Action", $Action)
    if ($systemRadio.Checked) { $args += "-UseSystemPython" }
    if ($DesktopDeps) { $args += "-DesktopDeps" }

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "powershell.exe"
    $psi.Arguments = ($args -join " ")
    $psi.WorkingDirectory = $RepoRoot
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true

    $p = New-Object System.Diagnostics.Process
    $p.StartInfo = $psi
    $p.EnableRaisingEvents = $true
    $p.add_OutputDataReceived([System.Diagnostics.DataReceivedEventHandler]{ param($s, $e) if ($e.Data) { Append-Output $e.Data } })
    $p.add_ErrorDataReceived([System.Diagnostics.DataReceivedEventHandler]{ param($s, $e) if ($e.Data) { Append-Output "[ERR] $($e.Data)" } })
    $p.add_Exited([System.EventHandler]{ param($s, $e) Set-Running $false "Finished with exit code $($s.ExitCode)" })

    $output.Clear()
    Append-Output "Repo: $RepoRoot"
    Append-Output "Action: $Action"
    Set-Running $true "Running $Action..."
    [void]$p.Start()
    $script:Process = $p
    $p.BeginOutputReadLine()
    $p.BeginErrorReadLine()
}

function New-ActionButton {
    param([string]$Text, [string]$Action, [bool]$DesktopDeps = $false)
    $btn = New-Object System.Windows.Forms.Button
    $btn.Text = $Text
    $btn.Size = New-Object System.Drawing.Size(136, 30)
    $btn.Add_Click({ Start-Action $Action $DesktopDeps }.GetNewClosure())
    $buttons.Controls.Add($btn)
}

New-ActionButton "Install deps" "install" $true
New-ActionButton "Run web app" "web" $false
New-ActionButton "Run desktop" "desktop" $true
New-ActionButton "Run tests" "test" $false
New-ActionButton "Build Windows" "build-windows" $true

$stopBtn = New-Object System.Windows.Forms.Button
$stopBtn.Text = "Stop"
$stopBtn.Size = New-Object System.Drawing.Size(90, 28)
$stopBtn.Enabled = $false
$stopBtn.Add_Click({
    if ($script:Process -ne $null -and -not $script:Process.HasExited) {
        $script:Process.Kill()
        Append-Output "Stopped by user."
        Set-Running $false "Stopped"
    }
})
$bottom.Controls.Add($stopBtn)

$clearBtn = New-Object System.Windows.Forms.Button
$clearBtn.Text = "Clear"
$clearBtn.Size = New-Object System.Drawing.Size(90, 28)
$clearBtn.Add_Click({ $output.Clear() })
$bottom.Controls.Add($clearBtn)

$saveBtn = New-Object System.Windows.Forms.Button
$saveBtn.Text = "Save log"
$saveBtn.Size = New-Object System.Drawing.Size(90, 28)
$saveBtn.Add_Click({
    $dialog = New-Object System.Windows.Forms.SaveFileDialog
    $dialog.Filter = "Text files|*.txt|All files|*.*"
    $dialog.FileName = "adb-device-manager-build-log.txt"
    if ($dialog.ShowDialog() -eq "OK") {
        [System.IO.File]::WriteAllText($dialog.FileName, $output.Text)
    }
})
$bottom.Controls.Add($saveBtn)

$form.Add_FormClosing({
    if ($script:Process -ne $null -and -not $script:Process.HasExited) {
        $script:Process.Kill()
    }
})

$form.Add_Shown({ $form.Activate() })
[void]$form.ShowDialog()
