# ---
# name: open_window_no_focus.ps1
# version: 1.0.0
# summary: Opens a new Windows Terminal window running a WSL script, raises it to the top so it is easy
#   to see, and gives keyboard focus back to the window the user was typing in. wt.exe has no
#   "open without activating" option, so this launches it, waits for the new window, restores the
#   previous foreground window, then raises the new one with SWP_NOACTIVATE. Used by handoff.sh.
# created: 2026-10-06
# last_updated: 2026-10-06
# maintainer: pvragon
# usage: powershell.exe -NoProfile -ExecutionPolicy Bypass -File open_window_no_focus.ps1 -Inner /linux/path/inner.sh
# ---
param([Parameter(Mandatory = $true)][string]$Inner)

Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public static class WinFocus {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint f);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
  public static List<IntPtr> Terminals() {
    var list = new List<IntPtr>();
    EnumWindows((h, l) => {
      var sb = new StringBuilder(256); GetClassName(h, sb, 256);
      if (sb.ToString() == "CASCADIA_HOSTING_WINDOW_CLASS" && IsWindowVisible(h)) list.Add(h);
      return true; }, IntPtr.Zero);
    return list;
  }
}
"@

$previous = [WinFocus]::GetForegroundWindow()
$before = [WinFocus]::Terminals()

Start-Process -FilePath "wt.exe" -ArgumentList @('-w', 'new', 'wsl.exe', '--', 'bash', $Inner)

# Wait up to 10 s for the new terminal window to appear.
$new = [IntPtr]::Zero
for ($i = 0; $i -lt 100 -and $new -eq [IntPtr]::Zero; $i++) {
  Start-Sleep -Milliseconds 100
  foreach ($h in [WinFocus]::Terminals()) { if (-not ($before -contains $h)) { $new = $h; break } }
}
if ($new -eq [IntPtr]::Zero) { Write-Output "window: not found; focus left as Windows set it"; exit 0 }
Start-Sleep -Milliseconds 300   # let the new window finish activating before taking focus back

# Give keyboard focus back. A tapped Alt key lets a background process call SetForegroundWindow.
if ($previous -ne [IntPtr]::Zero) {
  [WinFocus]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero)
  [WinFocus]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)
  [void][WinFocus]::SetForegroundWindow($previous)
}

# Raise the new window above the others without activating it: topmost, then back to normal.
$flags = 0x0001 -bor 0x0002 -bor 0x0010 -bor 0x0040   # NOSIZE | NOMOVE | NOACTIVATE | SHOWWINDOW
[void][WinFocus]::SetWindowPos($new, [IntPtr](-1), 0, 0, 0, 0, $flags)
[void][WinFocus]::SetWindowPos($new, [IntPtr](-2), 0, 0, 0, 0, $flags)

$focus = [WinFocus]::GetForegroundWindow()
Write-Output ("window: raised; focus " + $(if ($focus -eq $previous) { "returned to the previous window" } else { "NOT returned" }))
