"""
Filesystem Watchdog Service for Autonomous Crawler.

Monitors the incoming drop directory using the watchdog library,
debouncing file writes to ensure complete delivery before ingestion.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Callable, Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from backend.crawler.filter import FileIntegrityGate

logger = logging.getLogger(__name__)


class DebouncedDropHandler(FileSystemEventHandler):
    """
    Watches file system events on incoming drop directories and dispatches
    debounced notifications to the async crawler loop.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        on_file_ready: Callable[[Path], None],
        integrity_gate: Optional[FileIntegrityGate] = None,
        debounce_seconds: float = 1.0,
    ) -> None:
        super().__init__()
        self.loop = loop
        self.on_file_ready = on_file_ready
        self.integrity_gate = integrity_gate or FileIntegrityGate()
        self.debounce_seconds = debounce_seconds
        self._pending_tasks: dict[str, asyncio.TimerHandle] = {}

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._schedule_check(Path(str(event.src_path)))

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._schedule_check(Path(str(event.src_path)))

    def _schedule_check(self, file_path: Path) -> None:
        """Schedule a debounced stability verification in the event loop."""
        if file_path.name.startswith(".") or file_path.name.endswith(".tmp"):
            return

        key = str(file_path.resolve())

        # Cancel any prior scheduled check for this file
        if key in self._pending_tasks:
            self._pending_tasks[key].cancel()

        def _dispatch_verify():
            asyncio.create_task(self._verify_and_emit(file_path))

        timer = self.loop.call_later(self.debounce_seconds, _dispatch_verify)
        self._pending_tasks[key] = timer

    async def _verify_and_emit(self, file_path: Path) -> None:
        """Verify write completion and dispatch."""
        try:
            is_stable = await self.integrity_gate.wait_for_stability(
                file_path, check_interval=0.3, max_wait_seconds=4.0
            )
            if is_stable and file_path.exists():
                logger.info(f"Watchdog detected stable incoming file: {file_path.name}")
                self.on_file_ready(file_path)
        except Exception as e:
            logger.warning(f"Error checking file stability for {file_path}: {e}")


class DirectoryWatcher:
    """Manages the background watchdog observer thread."""

    def __init__(
        self,
        watch_dir: Path | str = "data/incoming",
        on_file_ready: Optional[Callable[[Path], None]] = None,
        debounce_seconds: float = 1.0,
    ) -> None:
        self.watch_dir = Path(watch_dir)
        self.on_file_ready = on_file_ready
        self.debounce_seconds = debounce_seconds
        self._observer: Optional[Observer] = None
        self._handler: Optional[DebouncedDropHandler] = None
        self._running = False

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        """Start the watchdog observer."""
        if self._running:
            return

        self.watch_dir.mkdir(parents=True, exist_ok=True)
        active_loop = loop or asyncio.get_event_loop()

        def _noop(p: Path):
            pass

        callback = self.on_file_ready or _noop
        self._handler = DebouncedDropHandler(
            loop=active_loop,
            on_file_ready=callback,
            debounce_seconds=self.debounce_seconds,
        )

        self._observer = Observer()
        self._observer.schedule(self._handler, str(self.watch_dir), recursive=False)
        self._observer.daemon = True
        self._observer.start()
        self._running = True
        logger.info(f"DirectoryWatcher observer started on {self.watch_dir}")

    def stop(self) -> None:
        """Stop the watchdog observer."""
        if not self._running or not self._observer:
            return
        try:
            self._observer.stop()
            self._observer.join(timeout=2.0)
        except Exception as e:
            logger.warning(f"Error stopping observer: {e}")
        finally:
            self._running = False
            self._observer = None
            logger.info("DirectoryWatcher observer stopped")

    @property
    def is_running(self) -> bool:
        return self._running
