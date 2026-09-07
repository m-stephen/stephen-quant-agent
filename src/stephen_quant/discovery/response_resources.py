"""Read-only process/kernel memory measurements, not model-scale guarantees."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone


def process_memory():
    if os.name == "nt":
        values = _windows_memory()
    else:
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        values = {
            "method": "getrusage",
            "peak_rss_bytes": int(peak if sys.platform == "darwin" else peak * 1024),
            "peak_private_commit_bytes": None,
            "physical_total_bytes": None,
            "physical_available_bytes": None,
        }
    return {"measured_at": datetime.now(timezone.utc).isoformat(), "pid": os.getpid(), **values}


def _windows_memory():
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (k, ctypes.c_size_t)
            for k in (
                "PeakWorkingSetSize",
                "WorkingSetSize",
                "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage",
                "PagefileUsage",
                "PeakPagefileUsage",
                "PrivateUsage",
            )
        ]

    class MemoryStatus(ctypes.Structure):
        _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD)] + [
            (k, ctypes.c_ulonglong)
            for k in (
                "ullTotalPhys",
                "ullAvailPhys",
                "ullTotalPageFile",
                "ullAvailPageFile",
                "ullTotalVirtual",
                "ullAvailVirtual",
                "ullAvailExtendedVirtual",
            )
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(Counters),
        wintypes.DWORD,
    ]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(
        kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb
    ):
        raise OSError(ctypes.get_last_error(), "process memory measurement unavailable")
    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(status)
    known = kernel.GlobalMemoryStatusEx(ctypes.byref(status))
    return {
        "method": "Windows GetProcessMemoryInfo/GlobalMemoryStatusEx",
        "peak_rss_bytes": int(counters.PeakWorkingSetSize),
        "current_rss_bytes": int(counters.WorkingSetSize),
        "peak_private_commit_bytes": int(counters.PeakPagefileUsage),
        "physical_total_bytes": int(status.ullTotalPhys) if known else None,
        "physical_available_bytes": int(status.ullAvailPhys) if known else None,
    }
