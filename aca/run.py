"""Start the ACA API (aca-firing-api) from any working directory.

`start.bat` runs this instead of `python -m uvicorn src.api.server:app` so that:

  * the `src` package is always importable (uvicorn's CLI needs the cwd to be the
    repo root, otherwise you get "No module named 'src'");
  * the server stops when the console window that started it is closed, instead of
    leaving a stray python.exe holding port 8420.

Usage:
    python run.py                     # 127.0.0.1:8420, stops when the launcher dies
    python run.py --port 8421
    python run.py --no-exit-with-parent   # keep running if the launcher goes away
"""

from __future__ import annotations

import argparse
import ctypes
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
POLL_SECONDS = 0.5
FORCE_EXIT_AFTER_SECONDS = 15.0

WAIT_TIMEOUT = 0x00000102
SYNCHRONIZE = 0x00100000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
ERROR_INVALID_PARAMETER = 87


class _ProcessBasicInformation(ctypes.Structure):
    """PROCESS_BASIC_INFORMATION from winternl.h, sized for 64-bit Windows."""

    _fields_ = [
        ("Reserved1", ctypes.c_void_p),
        ("PebBaseAddress", ctypes.c_void_p),
        ("Reserved2", ctypes.c_void_p * 2),
        ("UniqueProcessId", ctypes.c_void_p),
        ("InheritedFromUniqueProcessId", ctypes.c_void_p),
    ]


def _parent_pid() -> int:
    """PID of whoever launched us: the cmd.exe running start.bat, in normal use."""
    if os.name != "nt":
        return os.getppid()

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ntdll = ctypes.WinDLL("ntdll")
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p

    info = _ProcessBasicInformation()
    status = ntdll.NtQueryInformationProcess(
        ctypes.c_void_p(kernel32.GetCurrentProcess()),
        0,  # ProcessBasicInformation
        ctypes.byref(info),
        ctypes.sizeof(info),
        None,
    )
    if status != 0:
        return os.getppid()
    return int(info.InheritedFromUniqueProcessId or 0)


def _is_alive(pid: int) -> bool:
    if pid <= 0:
        # Unknown parent: never treat that as "the window closed".
        return True
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    handle = kernel32.OpenProcess(
        SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, False, pid
    )
    if not handle:
        # Gone (invalid parameter) vs. alive but not ours (access denied).
        return ctypes.get_last_error() != ERROR_INVALID_PARAMETER
    try:
        # WAIT_TIMEOUT means still running; a signaled handle means it exited.
        return kernel32.WaitForSingleObject(ctypes.c_void_p(handle), 0) == WAIT_TIMEOUT
    finally:
        kernel32.CloseHandle(ctypes.c_void_p(handle))


def _watch_parent(server: "object", parent_pid: int) -> None:
    while not getattr(server, "should_exit", False):
        time.sleep(POLL_SECONDS)
        if _is_alive(parent_pid):
            continue

        print(
            f"\n[run] the window that started this server is gone (pid {parent_pid}); stopping.",
            flush=True,
        )
        server.should_exit = True

        deadline = time.monotonic() + FORCE_EXIT_AFTER_SECONDS
        while time.monotonic() < deadline:
            if getattr(server, "finished", False):
                return
            time.sleep(0.2)

        print("[run] graceful shutdown timed out; forcing exit.", flush=True)
        os._exit(1)


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Start the ACA API server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8420)
    parser.add_argument(
        "--exit-with-parent",
        dest="exit_with_parent",
        action="store_true",
        default=True,
        help="stop when the process that launched this one exits (default)",
    )
    parser.add_argument(
        "--no-exit-with-parent",
        dest="exit_with_parent",
        action="store_false",
        help="keep running after the launcher exits",
    )
    args = parser.parse_args(argv)

    # src/api/server.py imports "src.*" absolutely, and the app reads data/ relative
    # to the repo root, so behave exactly like running from the repo root.
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    import uvicorn

    config = uvicorn.Config(
        "src.api.server:app", host=args.host, port=args.port, log_level="info"
    )
    server = uvicorn.Server(config)

    if args.exit_with_parent:
        parent_pid = _parent_pid()
        if parent_pid > 0:
            threading.Thread(
                target=_watch_parent,
                args=(server, parent_pid),
                name="parent-watchdog",
                daemon=True,
            ).start()
        else:
            print(
                "[run] could not read the parent process id; not following the console.",
                flush=True,
            )

    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
