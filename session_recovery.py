"""Recover work sessions left behind by an unexpected exit."""

from pathlib import Path
import ctypes
import json
import os

from pdf_ops import atomic_output


def process_is_alive(pid):
    if pid <= 0:
        return False
    if os.name == "nt":
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel.OpenProcess
        open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        open_process.restype = wintypes.HANDLE
        handle = open_process(0x00100000, False, pid)  # SYNCHRONIZE
        if not handle:
            return ctypes.get_last_error() == 5
        kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        try:
            return kernel.WaitForSingleObject(handle, 0) != 0
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class RecoveryJournal:
    def __init__(self, folder):
        self.path = folder / "recovery.json"
        self.last = None

    def write(self, documents):
        records = [
            dict(path=str(state.path), name=state.name, dirty=state.dirty, page=state.page,
                 saved_path=str(state.saved_path) if state.saved_path else None,
                 protected_source=str(state.protected_source) if state.protected_source else None,
                 redactions=state.redactions)
            for state in documents if state.dirty or state.redactions
        ]
        if not records:
            if self.last is not None:
                self.path.unlink(missing_ok=True)
                self.last = None
            return
        payload = json.dumps({"pid": os.getpid(), "documents": records}, ensure_ascii=False, sort_keys=True)
        if payload != self.last:
            with atomic_output(self.path) as temporary:
                temporary.write_text(payload, encoding="utf-8")
            self.last = payload


def interrupted_sessions(directory):
    for manifest in sorted(directory.glob("pdfiu-*/recovery.json")):
        try:
            journal = json.loads(manifest.read_text(encoding="utf-8"))
            if process_is_alive(int(journal["pid"])):
                continue
            records = [
                record for record in journal["documents"]
                if Path(record["path"]).is_file()
                and (not record["dirty"] or Path(record["path"]).resolve().is_relative_to(manifest.parent.resolve()))
            ]
        except (OSError, ValueError, TypeError, KeyError):
            continue
        if records:
            yield manifest, records


def retain_unrecovered(manifest, records):
    if not records:
        manifest.unlink(missing_ok=True)
        return
    journal = json.loads(manifest.read_text(encoding="utf-8"))
    journal["documents"] = records
    with atomic_output(manifest) as temporary:
        temporary.write_text(json.dumps(journal, ensure_ascii=False), encoding="utf-8")
