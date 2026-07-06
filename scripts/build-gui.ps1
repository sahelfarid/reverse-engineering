Add-Type -AssemblyName System.Windows.Forms, System.Drawing

# Compact Build GUI
# - Enter a build command, click Start to run it in a background process
# - Live stdout/stderr shown, Stop kills the process

[void][System.Reflection.Assembly]::LoadWithPartialName('System.Diagnostics')

$form = New-Object System.Windows.Forms.Form
$form.Text = 'Build Launcher'
$form.Size = New-Object System.Drawing.Size(700,480)
$form.StartPosition = 'CenterScreen'

$lbl = New-Object System.Windows.Forms.Label
$lbl.Text = 'Build command:'
$lbl.AutoSize = $true
$lbl.Location = New-Object System.Drawing.Point(10,12)
$form.Controls.Add($lbl)

$txtCmd = New-Object System.Windows.Forms.TextBox
$txtCmd.Location = New-Object System.Drawing.Point(12,30)
$txtCmd.Size = New-Object System.Drawing.Size(560,24)
$txtCmd.Text = 'py -3 -m pip install -r requirements.txt' # sensible default, change as needed
$form.Controls.Add($txtCmd)

$btnStart = New-Object System.Windows.Forms.Button
$btnStart.Location = New-Object System.Drawing.Point(580,28)
$btnStart.Size = New-Object System.Drawing.Size(90,24)
$btnStart.Text = 'Start'
$form.Controls.Add($btnStart)

$txtOutput = New-Object System.Windows.Forms.TextBox
$txtOutput.Multiline = $true
$txtOutput.ScrollBars = 'Both'
$txtOutput.ReadOnly = $true
$txtOutput.WordWrap = $false
$txtOutput.Font = New-Object System.Drawing.Font('Consolas',9)
$txtOutput.Location = New-Object System.Drawing.Point(12,64)
$txtOutput.Size = New-Object System.Drawing.Size(660,330)
$form.Controls.Add($txtOutput)

$btnStop = New-Object System.Windows.Forms.Button
$btnStop.Location = New-Object System.Drawing.Point(12,408)
$btnStop.Size = New-Object System.Drawing.Size(90,28)
$btnStop.Text = 'Stop'
$btnStop.Enabled = $false
$form.Controls.Add($btnStop)

$btnClear = New-Object System.Windows.Forms.Button
$btnClear.Location = New-Object System.Drawing.Point(110,408)
$btnClear.Size = New-Object System.Drawing.Size(90,28)
$btnClear.Text = 'Clear'
$form.Controls.Add($btnClear)

$btnOpenLog = New-Object System.Windows.Forms.Button
$btnOpenLog.Location = New-Object System.Drawing.Point(208,408)
$btnOpenLog.Size = New-Object System.Drawing.Size(90,28)
$btnOpenLog.Text = 'Save Log'
$form.Controls.Add($btnOpenLog)

$lblStatus = New-Object System.Windows.Forms.Label
$lblStatus.Location = New-Object System.Drawing.Point(320,412)
$lblStatus.Size = New-Object System.Drawing.Size(350,24)
$lblStatus.Text = 'Idle'
$form.Controls.Add($lblStatus)

# state
$global:proc = $null
$global:outEvents = @()

function Append-Output($s){
    if ($null -eq $s) { return }
    $action = [action]{ param($text) $txtOutput.AppendText($text + "`r`n") }
    $form.BeginInvoke($action, $s) | Out-Null
}

function Start-Build($command){
    if ($global:proc -ne $null -and -not $global:proc.HasExited){
        Append-Output 'A build is already running.'
        return
    }

    $lblStatus.Text = 'Starting...'
    $txtOutput.Clear()

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    # run under cmd to allow shell commands and path expansion; for unix-like commands use pwsh/sh explicitly
    $psi.FileName = 'cmd.exe'
    $psi.Arguments = "/c $command"
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true

    $p = New-Object System.Diagnostics.Process
    $p.StartInfo = $psi
    $p.EnableRaisingEvents = $true

    $outHandler = [System.Diagnostics.DataReceivedEventHandler]::new( {
        param($sender,$args)
        if ($args.Data){ Append-Output $args.Data }
    })
    $errHandler = [System.Diagnostics.DataReceivedEventHandler]::new( {
        param($sender,$args)
        if ($args.Data){ Append-Output "[ERR] $($args.Data)" }
    })

    $exitedHandler = [System.EventHandler]::new( {
        param($sender,$args)
        $form.BeginInvoke([action]{ $lblStatus.Text = 'Finished' }) | Out-Null
        $form.BeginInvoke([action]{ $btnStart.Enabled = $true; $btnStop.Enabled = $false }) | Out-Null
    })

    $p.add_OutputDataReceived($outHandler)
    $p.add_ErrorDataReceived($errHandler)
    $p.add_Exited($exitedHandler)

    $started = $p.Start()
    if ($started){
        $global:proc = $p
        $p.BeginOutputReadLine()
        $p.BeginErrorReadLine()
        $lblStatus.Text = 'Running'
        $btnStart.Enabled = $false
        $btnStop.Enabled = $true
        Append-Output "Started: $command"
    } else {
        Append-Output 'Failed to start process.'
    }
}

function Stop-Build(){
    if ($global:proc -ne $null -and -not $global:proc.HasExited){
        try{
            $global:proc.Kill()
            Append-Output 'Process killed by user.'
            $lblStatus.Text = 'Killed'
            $btnStart.Enabled = $true
            $btnStop.Enabled = $false
        } catch {
            Append-Output "Failed to stop process: $_"
        }
    } else {
        Append-Output 'No running process.'
    }
}

$btnStart.Add_Click({
    $cmd = $txtCmd.Text.Trim()
    if ([string]::IsNullOrWhiteSpace($cmd)){
        Append-Output 'Please enter a command.'
        return
    }
    Start-Build $cmd
})

$btnStop.Add_Click({ Stop-Build })

$btnClear.Add_Click({ $txtOutput.Clear() })

$btnOpenLog.Add_Click({
    $sfd = New-Object System.Windows.Forms.SaveFileDialog
    $sfd.Filter = 'Text files|*.txt|All files|*.*'
    $sfd.FileName = 'build-log.txt'
    if ($sfd.ShowDialog() -eq 'OK'){
        [System.IO.File]::WriteAllText($sfd.FileName, $txtOutput.Text)
    }
})

$form.Add_Shown({ $form.Activate() })
[void]$form.ShowDialog()