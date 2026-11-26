"""Worker process execution with Windows Job Object cancellation.

The child is created suspended, assigned to a kill-on-close job object, and
then resumed.  This closes the spawn/assign race: every descendant created by
the worker belongs to the job.  If the bridge process dies, Windows closes the
job handle and terminates the worker tree.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import threading
import time
from collections import deque
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TextIO

from .errors import WorkerError
from .redact import SecretRedactor

MAX_LINE_CHARS = 4 * 1024 * 1024
STDERR_TAIL_CHARS = 4000

CREATE_SUSPENDED = 0x00000004
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
JOB_OBJECT_BASIC_PROCESS_ID_LIST = 3
TH32CS_SNAPTHREAD = 0x00000004
THREAD_SUSPEND_RESUME = 0x0002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_TERMINATE = 0x0001
SYNCHRONIZE = 0x00100000
WAIT_TIMEOUT = 258
STILL_ACTIVE = 259


class _LARGE_INTEGER(ctypes.Structure):
    _fields_ = [("QuadPart", ctypes.c_longlong)]


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", _LARGE_INTEGER),
        ("PerJobUserTimeLimit", _LARGE_INTEGER),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _JOBOBJECT_BASIC_PROCESS_ID_LIST(ctypes.Structure):
    _fields_ = [
        ("NumberOfAssignedProcesses", wintypes.DWORD),
        ("NumberOfProcessIdsInList", wintypes.DWORD),
        ("ProcessIdList", ctypes.c_size_t * 1024),
    ]


class _THREADENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ThreadID", wintypes.DWORD),
        ("th32OwnerProcessID", wintypes.DWORD),
        ("tpBasePri", wintypes.LONG),
        ("tpDeltaPri", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
    ]


class _FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", wintypes.DWORD),
        ("dwHighDateTime", wintypes.DWORD),
    ]


if os.name == "nt":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    _kernel32.SetInformationJobObject.restype = wintypes.BOOL
    _kernel32.AssignProcessToJobObject.argtypes = [
        wintypes.HANDLE,
        wintypes.HANDLE,
    ]
    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _kernel32.TerminateJobObject.restype = wintypes.BOOL
    _kernel32.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    _kernel32.QueryInformationJobObject.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.OpenProcess.argtypes = [
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    ]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_FILETIME),
        ctypes.POINTER(_FILETIME),
        ctypes.POINTER(_FILETIME),
        ctypes.POINTER(_FILETIME),
    ]
    _kernel32.GetProcessTimes.restype = wintypes.BOOL
    _kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _kernel32.WaitForSingleObject.restype = wintypes.DWORD
    _kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _kernel32.TerminateProcess.restype = wintypes.BOOL
    _kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    _kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _kernel32.Thread32First.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_THREADENTRY32),
    ]
    _kernel32.Thread32First.restype = wintypes.BOOL
    _kernel32.Thread32Next.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_THREADENTRY32),
    ]
    _kernel32.Thread32Next.restype = wintypes.BOOL
    _kernel32.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenThread.restype = wintypes.HANDLE
    _kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
    _kernel32.ResumeThread.restype = wintypes.DWORD


@dataclass
class ProcessResult:
    exit_code: int | None
    timed_out: bool
    interrupted: bool
    duration_ms: int
    pid: int | None
    creation_time: int | None
    kill_verified: bool
    stdout_bytes: int
    stderr_bytes: int
    stderr_tail: str


class JobObject:
    def __init__(self) -> None:
        if os.name != "nt":
            raise WorkerError("Job Objects are only implemented on Windows")
        handle = _kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise WorkerError(
                "CreateJobObject failed", win_error=ctypes.get_last_error()
            )
        self.handle: int | None = int(handle)
        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not _kernel32.SetInformationJobObject(
            handle,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
        ):
            error = ctypes.get_last_error()
            self.close()
            raise WorkerError("SetInformationJobObject failed", win_error=error)

    def assign(self, process_handle: Any) -> None:
        if self.handle is None:
            raise WorkerError("Job object is closed")
        if not _kernel32.AssignProcessToJobObject(
            self.handle, ctypes.c_void_p(int(process_handle))
        ):
            raise WorkerError(
                "AssignProcessToJobObject failed",
                win_error=ctypes.get_last_error(),
            )

    def process_ids(self) -> list[int]:
        if self.handle is None:
            return []
        info = _JOBOBJECT_BASIC_PROCESS_ID_LIST()
        if not _kernel32.QueryInformationJobObject(
            self.handle,
            JOB_OBJECT_BASIC_PROCESS_ID_LIST,
            ctypes.byref(info),
            ctypes.sizeof(info),
            None,
        ):
            return []
        count = min(int(info.NumberOfProcessIdsInList), 1024)
        return [int(info.ProcessIdList[index]) for index in range(count)]

    def terminate(self) -> bool:
        if self.handle is None:
            return True
        return bool(_kernel32.TerminateJobObject(self.handle, 1))

    def close(self) -> None:
        if self.handle is not None:
            _kernel32.CloseHandle(self.handle)
            self.handle = None


def _process_creation_time(pid: int) -> int | None:
    if os.name != "nt":
        return None
    handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        creation = _FILETIME()
        exit_time = _FILETIME()
        kernel = _FILETIME()
        user = _FILETIME()
        if not _kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            return None
        return (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)
    finally:
        _kernel32.CloseHandle(handle)


def process_alive(pid: int, creation_time: int | None) -> bool | None:
    """Return True/False, or None when the process state cannot be queried."""

    if os.name != "nt":
        return None
    handle = _kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid
    )
    if not handle:
        error = ctypes.get_last_error()
        if error == 87:  # ERROR_INVALID_PARAMETER: no such process
            return False
        return None
    try:
        if creation_time is not None:
            actual = _process_creation_time(pid)
            if actual is not None and actual != creation_time:
                return False
        wait = _kernel32.WaitForSingleObject(handle, 0)
        if wait == WAIT_TIMEOUT:
            return True
        if wait == 0:
            return False
        return None
    finally:
        _kernel32.CloseHandle(handle)


def _resume_process(pid: int) -> None:
    if os.name != "nt":
        return
    snapshot = _kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    if not snapshot or int(snapshot) == -1:
        raise WorkerError(
            "CreateToolhelp32Snapshot failed", win_error=ctypes.get_last_error()
        )
    resumed = 0
    try:
        entry = _THREADENTRY32()
        entry.dwSize = ctypes.sizeof(_THREADENTRY32)
        if not _kernel32.Thread32First(snapshot, ctypes.byref(entry)):
            raise WorkerError(
                "Thread32First failed", win_error=ctypes.get_last_error()
            )
        while True:
            if int(entry.th32OwnerProcessID) == pid:
                thread = _kernel32.OpenThread(
                    THREAD_SUSPEND_RESUME, False, int(entry.th32ThreadID)
                )
                if thread:
                    _kernel32.ResumeThread(thread)
                    _kernel32.CloseHandle(thread)
                    resumed += 1
            if not _kernel32.Thread32Next(snapshot, ctypes.byref(entry)):
                break
    finally:
        _kernel32.CloseHandle(snapshot)
    if resumed == 0:
        raise WorkerError("Could not resume the suspended worker process")


def _pump(
    stream: TextIO,
    destination: Path,
    redactor: SecretRedactor,
    tail: deque[str],
    counter: list[int],
) -> None:
    try:
        with destination.open("w", encoding="utf-8", newline="\n") as output:
            for line in stream:
                if len(line) > MAX_LINE_CHARS:
                    line = line[:MAX_LINE_CHARS] + "\n[BRIDGE_TRUNCATED_LINE]\n"
                clean = redactor.redact(line)
                output.write(clean)
                tail.append(clean)
                counter[0] += len(clean.encode("utf-8", "replace"))
                while sum(len(item) for item in tail) > STDERR_TAIL_CHARS * 2:
                    tail.popleft()
    except (OSError, ValueError):
        return


def run_worker(
    argv: list[str],
    *,
    cwd: str | Path,
    env: dict[str, str],
    stdout_path: str | Path,
    stderr_path: str | Path,
    timeout_seconds: float,
    redactor: SecretRedactor,
    on_start: Callable[[int, int | None], None] | None = None,
) -> ProcessResult:
    if not argv or not all(isinstance(item, str) for item in argv):
        raise WorkerError("Worker argv is invalid")
    stdout_target = Path(stdout_path)
    stderr_target = Path(stderr_path)
    stdout_target.parent.mkdir(parents=True, exist_ok=True)
    stderr_target.parent.mkdir(parents=True, exist_ok=True)

    job = JobObject()
    process: subprocess.Popen[str] | None = None
    started = time.monotonic()
    stdout_tail: deque[str] = deque()
    stderr_tail: deque[str] = deque()
    stdout_count = [0]
    stderr_count = [0]
    threads: list[threading.Thread] = []
    timed_out = False
    interrupted = False
    kill_verified = True
    pid: int | None = None
    creation_time: int | None = None
    try:
        flags = CREATE_SUSPENDED | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        try:
            process = subprocess.Popen(
                argv,
                cwd=str(cwd),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=flags,
            )
        except OSError as exc:
            raise WorkerError(
                "Worker process could not be started", error=str(exc)
            ) from exc

        pid = process.pid
        creation_time = _process_creation_time(pid)
        try:
            job.assign(process._handle)  # type: ignore[attr-defined]
            _resume_process(pid)
        except BaseException:
            job.terminate()
            process.kill()
            process.wait(timeout=10)
            raise

        if on_start is not None:
            on_start(pid, creation_time)

        assert process.stdout is not None
        assert process.stderr is not None
        stdout_thread = threading.Thread(
            target=_pump,
            args=(process.stdout, stdout_target, redactor, stdout_tail, stdout_count),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=_pump,
            args=(process.stderr, stderr_target, redactor, stderr_tail, stderr_count),
            daemon=True,
        )
        threads = [stdout_thread, stderr_thread]
        for thread in threads:
            thread.start()

        deadline = started + max(0.1, float(timeout_seconds))
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            try:
                process.wait(timeout=min(0.25, remaining))
                break
            except subprocess.TimeoutExpired:
                continue

        if timed_out:
            job.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)

        for thread in threads:
            thread.join(timeout=5)

        # Kill any descendants that outlived the main worker.  Standalone
        # OpenCode should not leave a server behind; a lingering child is a
        # cancellation risk and is reported.
        if not timed_out:
            lingering = job.process_ids()
            if lingering:
                job.terminate()
                for _ in range(20):
                    if not job.process_ids():
                        break
                    time.sleep(0.1)
        for _ in range(20):
            if not job.process_ids():
                break
            time.sleep(0.1)
        if job.process_ids():
            for child_pid in job.process_ids():
                handle = _kernel32.OpenProcess(PROCESS_TERMINATE, False, child_pid)
                if handle:
                    _kernel32.TerminateProcess(handle, 1)
                    _kernel32.CloseHandle(handle)
            time.sleep(0.2)
        kill_verified = not job.process_ids()

        exit_code = process.returncode
        return ProcessResult(
            exit_code=exit_code,
            timed_out=timed_out,
            interrupted=interrupted,
            duration_ms=int((time.monotonic() - started) * 1000),
            pid=pid,
            creation_time=creation_time,
            kill_verified=kill_verified,
            stdout_bytes=stdout_count[0],
            stderr_bytes=stderr_count[0],
            stderr_tail="".join(stderr_tail)[-STDERR_TAIL_CHARS:],
        )
    except KeyboardInterrupt:
        interrupted = True
        job.terminate()
        if process is not None:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        for thread in threads:
            thread.join(timeout=5)
        job.close()
        raise
    finally:
        job.close()
