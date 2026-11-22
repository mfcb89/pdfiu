"""Local rotating error log for PDFiu (no telemetry, stored only on disk)."""

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import platform
import sys
import threading


def log_directory(app_name="PDFiu"):
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        return base / app_name / "logs"
    return Path.home() / ".local" / "state" / app_name / "logs"


def setup_logging(app_name="PDFiu", app_version="0.0.0", *, directory=None):
    target_dir = Path(directory) if directory is not None else log_directory(app_name)
    target_dir.mkdir(parents=True, exist_ok=True)
    log_file = target_dir / "pdfiu.log"

    logger = logging.getLogger("pdfiu")
    logger.setLevel(logging.INFO)
    if not any(isinstance(h, RotatingFileHandler) and Path(h.baseFilename) == log_file for h in logger.handlers):
        handler = RotatingFileHandler(log_file, maxBytes=512 * 1024, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(handler)

    logger.info("Start %s %s (%s %s)", app_name, app_version, platform.system(), platform.release())

    previous_sys_hook = sys.excepthook

    def handle_exception(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            previous_sys_hook(exc_type, exc_value, exc_tb)
            return
        logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))
        previous_sys_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = handle_exception

    if hasattr(threading, "excepthook"):
        previous_thread_hook = threading.excepthook

        def handle_thread_exception(args):
            logger.critical(
                "Unhandled thread exception in %s",
                getattr(args.thread, "name", "thread"),
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )
            previous_thread_hook(args)

        threading.excepthook = handle_thread_exception

    return log_file
