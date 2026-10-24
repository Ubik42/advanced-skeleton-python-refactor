param(
    [string]$Module = "maya_custom_squash_parity",
    [int]$TimeoutSeconds = 300,
    [switch]$AllowOtherMaya
)
$ErrorActionPreference = "Stop"
$testRoot = Split-Path -Parent $PSScriptRoot
if ($Module -notmatch '^[a-zA-Z_][a-zA-Z0-9_]*$') { throw '测试模块名无效' }
$testEntry = Join-Path $PSScriptRoot ($Module + '.py')
if (-not (Test-Path -LiteralPath $testEntry)) { throw "测试入口不存在：$testEntry" }
$testActive = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(maya|mayabatch|mayapy)\.exe$' })
$testOwnActive = @($testActive | Where-Object {
    $_.CommandLine -and $_.CommandLine.Replace('\', '/') -like ('*' + $testRoot.Replace('\', '/') + '/validation*')
})
if ($testOwnActive.Count -or ($testActive.Count -and -not $AllowOtherMaya)) {
    $testActive | Select-Object ProcessId, Name, CommandLine | Format-List | Out-String | Write-Output
    throw '已有本工程验证实例，或尚未允许其他任务并行；本任务不再重复启动'
}
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class AdvTestDpi {
    [DllImport("user32.dll")]
    public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
}
'@
# Read monitor work areas and move the native window in one per-monitor DPI
# coordinate system. Mixed display scaling otherwise virtualizes these values.
$testPreviousDpi = [AdvTestDpi]::SetThreadDpiAwarenessContext([IntPtr](-4))
Add-Type -AssemblyName System.Windows.Forms
$testScreens = @([System.Windows.Forms.Screen]::AllScreens | Where-Object { -not $_.Primary })
if (-not $testScreens.Count) { throw '未检测到副屏，停止图形测试以免占用主屏' }
$testArea = $testScreens[0].WorkingArea
$testHeight = [int][Math]::Floor($testArea.Height / 2)
$testX = $testArea.X
$testY = $testArea.Y + $testArea.Height - $testHeight
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class AdvTestWindow {
    [StructLayout(LayoutKind.Sequential)]
    public struct Rect { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll", SetLastError=true)]
    public static extern bool GetWindowRect(IntPtr hwnd, out Rect rect);
    [DllImport("user32.dll", SetLastError=true)]
    public static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int w, int h, uint flags);
}
'@
$testValidation = $PSScriptRoot.Replace('\','/')
$testCommand = 'python("import sys;sys.path.insert(0,r''' + $testValidation + ''');import ' + $Module + ' as suite;from maya import utils;utils.executeDeferred(suite.main,standalone=False,quit_on_finish=True)")'
$testOutput = Join-Path $testRoot 'validation\results'
[System.IO.Directory]::CreateDirectory($testOutput) | Out-Null
$testLog = Join-Path $testOutput ($Module + '-gui.log')
$env:MAYA_DISABLE_CIP = '1'
$env:MAYA_UI_LANGUAGE = 'en_US'
$testCompletion = Join-Path $testRoot ("local\maya-completed-" + [Guid]::NewGuid().ToString("N") + ".json")
$env:ADV_TEST_COMPLETION_FILE = $testCompletion
$testProcess = $null
$testFinished = $null
try {
    $testProcess = Start-Process -FilePath 'C:\Program Files\Autodesk\Maya2024\bin\maya.exe' -ArgumentList @(
        '-noAutoloadPlugins', '-command', ('"' + $testCommand.Replace('"','\"') + '"'),
        '-log', ('"' + $testLog.Replace('\','/') + '"')) -WindowStyle Hidden -PassThru
    $testProcess.Id | Set-Content -LiteralPath (Join-Path $testRoot 'local\current-test-maya.pid')
    Write-Output "Maya test PID $($testProcess.Id); secondary lower area ($testX,$testY,$($testArea.Width),$testHeight)"
    $testDeadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $testPlaced = [IntPtr]::Zero
    while (-not $testProcess.WaitForExit(500)) {
        if ([DateTime]::UtcNow -gt $testDeadline) { throw 'Maya 测试超时，清理本任务进程' }
        if (Test-Path -LiteralPath $testCompletion) {
            $testFinished = Get-Content -LiteralPath $testCompletion -Raw | ConvertFrom-Json
            if ($testFinished.pid -ne $testProcess.Id) { throw '测试完成记录的进程身份不匹配' }
            if (-not $testProcess.WaitForExit(5000)) {
                Stop-Process -Id $testProcess.Id -Force
                $testProcess.WaitForExit(10000) | Out-Null
                Write-Output '测试已完成，已清理未自行退出的本任务 Maya 实例'
            }
            break
        }
        $testProcess.Refresh()
        $testHandle = $testProcess.MainWindowHandle
        $testNeedsPlacement = $testHandle -ne $testPlaced
        if ($testHandle -ne [IntPtr]::Zero) {
            $testRect = New-Object AdvTestWindow+Rect
            if (-not [AdvTestWindow]::GetWindowRect($testHandle,[ref]$testRect)) {
                throw '无法核实本任务 Maya 窗口位置'
            }
            $testNeedsPlacement = $testNeedsPlacement -or (
                $testRect.Left -ne $testX -or $testRect.Top -ne $testY -or
                ($testRect.Right - $testRect.Left) -ne $testArea.Width -or
                ($testRect.Bottom - $testRect.Top) -ne $testHeight)
        }
        if ($testHandle -ne [IntPtr]::Zero -and $testNeedsPlacement) {
            # SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW
            if (-not [AdvTestWindow]::SetWindowPos($testHandle,[IntPtr]::Zero,$testX,$testY,$testArea.Width,$testHeight,0x0054)) {
                throw 'Maya 窗口无法放入副屏下半区'
            }
            $testPlaced = $testHandle
        }
    }
    Write-Output "Maya test process exited: PID $($testProcess.Id), exit code $($testProcess.ExitCode)"
    if (-not $testFinished -and (Test-Path -LiteralPath $testCompletion)) {
        $testFinished = Get-Content -LiteralPath $testCompletion -Raw | ConvertFrom-Json
    }
    if (-not $testFinished -or $testFinished.pid -ne $testProcess.Id) {
        throw 'Maya 已退出，但没有匹配本任务进程的测试完成记录'
    }
    if ($testFinished.status -ne 'passed') {
        throw "Maya 测试未通过：$($testFinished.status)，详见本地报告"
    }
} finally {
    if ($testProcess) {
        $testProcess.Refresh()
        if (-not $testProcess.HasExited) {
            # This is exactly the process created above, never a user session.
            Stop-Process -Id $testProcess.Id -Force
            $testProcess.WaitForExit(10000) | Out-Null
        }
        if (Get-Process -Id $testProcess.Id -ErrorAction SilentlyContinue) { throw '本任务 Maya 进程仍未退出' }
    }
    if ($testPreviousDpi -ne [IntPtr]::Zero) {
        [AdvTestDpi]::SetThreadDpiAwarenessContext($testPreviousDpi) | Out-Null
    }
}
