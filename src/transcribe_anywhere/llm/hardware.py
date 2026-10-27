"""Is this computer strong enough for a local LLM, and which model fits?"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class Hardware:
    cpu: str
    cores: int
    ram_gb: float
    gpu: str = ""
    vram_gb: float = 0.0


@dataclass
class Advice:
    level: str          # "good" | "ok" | "slow" | "no"
    headline: str
    detail: str
    model: str          # recommended Ollama model
    num_ctx: int        # context window to request
    correction_ok: bool


def detect() -> Hardware:
    gpu, vram = _nvidia()
    return Hardware(_cpu_name(), os.cpu_count() or 1, _ram_gb(), gpu, vram)


def advise(hw: Hardware) -> Advice:
    if hw.vram_gb >= 20:
        return Advice("good", "Sehr gut geeignet",
                      f"{hw.gpu} mit {hw.vram_gb:.0f} GB – großes Modell, schnelle Zusammenfassung und Korrektur.",
                      "qwen3.5:27b", 16384, True)
    if hw.vram_gb >= 10:
        return Advice("good", "Gut geeignet",
                      f"{hw.gpu} mit {hw.vram_gb:.0f} GB – Zusammenfassung und Korrektur laufen zügig.",
                      "qwen3.5:9b", 16384, True)
    if hw.vram_gb >= 6:
        return Advice("ok", "Geeignet",
                      f"{hw.gpu} mit {hw.vram_gb:.0f} GB – kleines Modell, Zusammenfassung und Korrektur möglich.",
                      "gemma3:4b", 8192, True)
    if hw.ram_gb >= 15:
        return Advice("slow", "Nur Zusammenfassung empfohlen",
                      f"Keine passende Grafikkarte, {hw.ram_gb:.0f} GB RAM – ein kleines Modell läuft auf dem "
                      "Prozessor. Die Zusammenfassung dauert einige Minuten; eine Korrektur des ganzen "
                      "Transkripts würde sehr lange dauern.",
                      "gemma3:4b", 8192, False)
    return Advice("no", "Nicht ausreichend",
                  f"Nur {hw.ram_gb:.0f} GB RAM und keine passende Grafikkarte – ein lokales Sprachmodell "
                  "wäre zu langsam.", "", 4096, False)


# --------------------------------------------------------------------------- probes
def _nvidia() -> tuple[str, float]:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout.strip().splitlines()
        name, mem = out[0].rsplit(",", 1)
        return name.strip(), float(mem) / 1024
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return "", 0.0


def _ram_gb() -> float:
    try:
        if sys.platform == "win32":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(stat)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return stat.ullTotalPhys / 1024**3
        if sys.platform == "darwin":
            out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout
            return int(out) / 1024**3
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / 1024**2
    except (OSError, ValueError, AttributeError):
        pass
    return 0.0


def _cpu_name() -> str:
    try:
        if sys.platform == "win32":
            import winreg

            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            return winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except (OSError, ImportError):
        pass
    return platform.processor() or "Unbekannte CPU"
