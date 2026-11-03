"""Windows: app identity, icon and shortcuts (Desktop, Start menu) so the app can be pinned.

Windows does not let programs pin themselves to the taskbar. What we can do:
- give the process its own AppUserModelID, so its taskbar button is "Transcribe Anywhere"
  (with our icon) instead of "Python";
- create shortcuts that carry the same ID and our icon. Right-click → "An Taskleiste anheften"
  then pins the real app, and pinning the running window works as well.

Shortcuts are written by a PowerShell child process: with the Microsoft Store Python, writes
from Python itself into %APPDATA% (Start menu) are silently redirected and Windows never sees them.
"""

from __future__ import annotations

import base64
import subprocess
import sys
from pathlib import Path

APP_ID = "Ehrenfried.TranscribeAnywhere"
LINK_NAME = "Transcribe Anywhere"
ICON = Path(__file__).parent / "assets" / "app.ico"


def set_process_app_id() -> None:
    """Call before the first window is shown."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass


def launch_target() -> tuple[str, str, str]:
    """(program, arguments, working directory) that start the app without a console window."""
    exe = Path(sys.executable)
    if getattr(sys, "frozen", False):                       # PyInstaller build
        return str(exe), "", str(exe.parent)
    gui = exe.parent / "transcribe-anywhere.exe"            # venv launcher from [project.gui-scripts]
    project = Path(__file__).resolve().parents[2]
    if gui.exists():
        return str(gui), "", str(project)
    pythonw = exe.with_name("pythonw.exe")
    return str(pythonw if pythonw.exists() else exe), "-m transcribe_anywhere", str(project)


def ensure_icon() -> Path:
    if not ICON.exists():
        from PySide6.QtGui import QGuiApplication

        from transcribe_anywhere.ui.theme import write_ico

        if QGuiApplication.instance() is None:          # Qt needs an app object to paint
            ensure_icon.qt_app = QGuiApplication([])
        ICON.parent.mkdir(parents=True, exist_ok=True)
        write_ico(ICON)
    return ICON


_CSHARP = r"""
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;

[ComImport, Guid("000214F9-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IShellLinkW {
    void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder f, int c, IntPtr fd, uint fl);
    void GetIDList(out IntPtr p);
    void SetIDList(IntPtr p);
    void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder s, int c);
    void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string s);
    void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder s, int c);
    void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string s);
    void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder s, int c);
    void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string s);
    void GetHotkey(out short h);
    void SetHotkey(short h);
    void GetShowCmd(out int c);
    void SetShowCmd(int c);
    void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder s, int c, out int i);
    void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string s, int i);
    void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string s, uint r);
    void Resolve(IntPtr h, uint f);
    void SetPath([MarshalAs(UnmanagedType.LPWStr)] string s);
}

[StructLayout(LayoutKind.Sequential, Pack = 4)]
public struct TaPropertyKey { public Guid fmtid; public uint pid; }

[StructLayout(LayoutKind.Explicit, Size = 24)]
public struct TaPropVariant { [FieldOffset(0)] public ushort vt; [FieldOffset(8)] public IntPtr p; }

[ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IPropertyStore {
    void GetCount(out uint c);
    void GetAt(uint i, out TaPropertyKey k);
    void GetValue(ref TaPropertyKey k, out TaPropVariant v);
    void SetValue(ref TaPropertyKey k, ref TaPropVariant v);
    void Commit();
}

[ComImport, Guid("00021401-0000-0000-C000-000000000046")]
class CShellLink {}

public static class TaShortcut {
    public static void Create(string lnk, string target, string args, string workdir,
                              string icon, string desc, string appId) {
        var link = (IShellLinkW)new CShellLink();
        link.SetPath(target);
        link.SetArguments(args);
        link.SetWorkingDirectory(workdir);
        link.SetIconLocation(icon, 0);
        link.SetDescription(desc);
        var store = (IPropertyStore)link;
        var key = new TaPropertyKey { fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), pid = 5 };
        var value = new TaPropVariant { vt = 31, p = Marshal.StringToCoTaskMemUni(appId) };   // VT_LPWSTR
        try { store.SetValue(ref key, ref value); store.Commit(); }
        finally { Marshal.FreeCoTaskMem(value.p); }
        ((IPersistFile)link).Save(lnk, true);
    }
}
"""


def _ps_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _run_powershell(script: str) -> subprocess.CompletedProcess:
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-EncodedCommand", encoded],
        capture_output=True, text=True, timeout=120,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _folders_ps() -> str:
    return ("$folders = @{ desktop = [Environment]::GetFolderPath('Desktop'); "
            "startmenu = (Join-Path ([Environment]::GetFolderPath('ApplicationData')) "
            "'Microsoft\\Windows\\Start Menu\\Programs') }\n")


def create_shortcuts(desktop: bool = True, start_menu: bool = True) -> list[str]:
    """Create the shortcuts; returns their paths. Raises RuntimeError with a readable message."""
    if sys.platform != "win32":
        raise RuntimeError("Verknüpfungen gibt es nur unter Windows.")
    target, args, workdir = launch_target()
    icon = ensure_icon()
    places = [p for p, on in (("desktop", desktop), ("startmenu", start_menu)) if on]
    script = (
        "$ErrorActionPreference = 'Stop'\n"
        f"Add-Type -TypeDefinition @'\n{_CSHARP}\n'@\n"
        + _folders_ps()
        + f"foreach ($place in @({', '.join(_ps_quote(p) for p in places)})) {{\n"
        f"  $lnk = Join-Path $folders[$place] {_ps_quote(LINK_NAME + '.lnk')}\n"
        f"  [TaShortcut]::Create($lnk, {_ps_quote(target)}, {_ps_quote(args)}, {_ps_quote(workdir)}, "
        f"{_ps_quote(str(icon))}, {_ps_quote('Meetings lokal transkribieren')}, {_ps_quote(APP_ID)})\n"
        "  Write-Output $lnk\n"
        "}\n"
    )
    result = _run_powershell(script)
    if result.returncode != 0:
        raise RuntimeError(f"Verknüpfung konnte nicht angelegt werden: {result.stderr.strip()[-400:]}")
    return [line.strip() for line in result.stdout.splitlines() if line.strip().endswith(".lnk")]


def existing_shortcuts() -> dict[str, bool]:
    """Which shortcuts exist (checked by PowerShell, which sees the real folders)."""
    if sys.platform != "win32":
        return {"desktop": False, "startmenu": False}
    script = (_folders_ps()
              + "foreach ($k in $folders.Keys) { $k + '=' + "
              f"(Test-Path (Join-Path $folders[$k] {_ps_quote(LINK_NAME + '.lnk')})) }}\n")
    try:
        out = _run_powershell(script).stdout
    except Exception:
        return {"desktop": False, "startmenu": False}
    found = dict(line.strip().split("=", 1) for line in out.splitlines() if "=" in line)
    return {k: found.get(k, "False") == "True" for k in ("desktop", "startmenu")}


def remove_shortcuts() -> None:
    if sys.platform != "win32":
        return
    script = (_folders_ps()
              + "foreach ($k in $folders.Keys) { Remove-Item -LiteralPath (Join-Path $folders[$k] "
              f"{_ps_quote(LINK_NAME + '.lnk')}) -ErrorAction SilentlyContinue }}\n")
    _run_powershell(script)
