# Answers an open file dialog by UI Automation: finds the window whose title starts with -Title,
# writes -Path into its file-name box and presses Open. Used by the journey tests to drive the
# native dialog of the real Studio without keystrokes (which Windows may not deliver to a
# background window). Prints "ok" or the reason it could not.
param([Parameter(Mandatory)] [string] $Title, [Parameter(Mandatory)] [string] $Path, [int] $TimeoutS = 15)
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement
$isWindow = New-Object System.Windows.Automation.PropertyCondition ([System.Windows.Automation.AutomationElement]::ControlTypeProperty), ([System.Windows.Automation.ControlType]::Window)
$isEdit = New-Object System.Windows.Automation.PropertyCondition ([System.Windows.Automation.AutomationElement]::ControlTypeProperty), ([System.Windows.Automation.ControlType]::Edit)
$isButton = New-Object System.Windows.Automation.PropertyCondition ([System.Windows.Automation.AutomationElement]::ControlTypeProperty), ([System.Windows.Automation.ControlType]::Button)
$deadline = (Get-Date).AddSeconds($TimeoutS)
$dlg = $null
while (-not $dlg -and (Get-Date) -lt $deadline) {
    foreach ($w in $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $isWindow)) {
        if ($w.Current.Name -like "$Title*") { $dlg = $w; break }
    }
    if (-not $dlg) { Start-Sleep -Milliseconds 250 }
}
if (-not $dlg) { Write-Output "no dialog"; exit 1 }
# The file-name box of the common dialog has automation id 1148; fall back to the last edit box.
$edits = $dlg.FindAll([System.Windows.Automation.TreeScope]::Descendants, $isEdit)
$box = $null
foreach ($e in $edits) { if ($e.Current.AutomationId -eq '1148') { $box = $e; break } }
Add-Type -AssemblyName System.Windows.Forms
if (-not $box) {
    # The file-name box is not always in the automation tree: give the dialog the focus through
    # UI Automation (allowed across processes), then type into its file-name box (Alt+N).
    $dlg.SetFocus()
    Start-Sleep -Milliseconds 400
    $esc = ($Path.ToCharArray() | ForEach-Object { if ('+^%~(){}[]'.Contains($_)) { '{' + $_ + '}' } else { [string]$_ } }) -join ''
    [System.Windows.Forms.SendKeys]::SendWait('%n')
    Start-Sleep -Milliseconds 300
    [System.Windows.Forms.SendKeys]::SendWait($esc)
    Start-Sleep -Milliseconds 300
    [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
    Write-Output "ok"
    exit 0
}
$box.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue($Path)
Start-Sleep -Milliseconds 300
$open = $null
foreach ($b in $dlg.FindAll([System.Windows.Automation.TreeScope]::Descendants, $isButton)) {
    if ($b.Current.AutomationId -eq '1') { $open = $b; break }
}
if (-not $open) {
    foreach ($b in $dlg.FindAll([System.Windows.Automation.TreeScope]::Descendants, $isButton)) {
        if ($b.Current.Name -match '^(&?Open|&?Abrir)') { $open = $b; break }
    }
}
if ($open) {
    $open.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
} else {
    # Some dialogs expose Open as a split button without the invoke pattern: focus the file-name
    # box through UI Automation and press Enter in it.
    $box.SetFocus()
    Start-Sleep -Milliseconds 300
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
}
Write-Output "ok"
