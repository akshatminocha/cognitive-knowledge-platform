"""
Crawler Service & Asynchronous Ingestion Queue.

Orchestrates 24/7 background intake across local drop folders, cloud buckets,
SFTP endpoints, and incoming webhooks, feeding directly into IngestionPipeline.
"""

from __future__ import annotations

import asyncio
import datetime
import enum
import logging
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from backend.crawler.connectors import (
    BaseStorageConnector,
    GCSStorageConnector,
    LocalWatchdogConnector,
    SFTPStorageConnector,
    S3StorageConnector,
    AzureBlobStorageConnector,
)
from backend.crawler.filter import DomainFilter, FileIntegrityGate
from backend.crawler.watcher import DirectoryWatcher
from backend.ingestion.pipeline import IngestionPipeline

logger = logging.getLogger(__name__)


class CrawlerStatus(str, enum.Enum):
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass
class CrawlerEvent:
    """Record of an autonomous crawler ingestion event."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    filename: str = ""
    file_path: Optional[str] = None
    source: str = "local_watchdog"
    detected_domain: str = "healthtech"
    confidence: float = 1.0
    status: str = "pending"  # pending, processing, success, failed, filtered
    chunks_created: int = 0
    entities_extracted: int = 0
    relationships_extracted: int = 0
    duration_ms: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    error_message: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CrawlerService:
    """
    Autonomous crawler engine running in the FastAPI background.
    Manages filesystem watchdog, remote storage connectors, debounce gate,
    and background worker task.
    """

    def __init__(
        self,
        watch_dir: Path | str = "data/incoming",
        gateway: Any = None,
        ontology_manager: Any = None,
        qdrant_client: Any = None,
        neo4j_driver: Any = None,
        poll_interval_seconds: float = 15.0,
        max_log_entries: int = 200,
    ) -> None:
        self.watch_dir = Path(watch_dir)
        self.gateway = gateway
        self.ontology_manager = ontology_manager
        self.qdrant_client = qdrant_client
        self.neo4j_driver = neo4j_driver
        self.poll_interval = poll_interval_seconds

        self.status = CrawlerStatus.STOPPED
        self.filter = DomainFilter()
        self.integrity_gate = FileIntegrityGate()

        # Connectors registry
        self.local_connector = LocalWatchdogConnector(watch_dir=self.watch_dir)
        self.gcs_connector = GCSStorageConnector()
        self.sftp_connector = SFTPStorageConnector()
        self.s3_connector = S3StorageConnector()
        self.azure_connector = AzureBlobStorageConnector()

        self.connectors: list[BaseStorageConnector] = [
            self.local_connector,
            self.gcs_connector,
            self.sftp_connector,
            self.s3_connector,
            self.azure_connector,
        ]

        self.watcher = DirectoryWatcher(
            watch_dir=self.watch_dir,
            on_file_ready=self._on_watchdog_file,
            debounce_seconds=1.0,
        )

        # Internal queue and event logs
        self._queue: asyncio.Queue[tuple[Path, str, Optional[str], Optional[dict], CrawlerEvent]] = asyncio.Queue()
        self._logs: deque[CrawlerEvent] = deque(maxlen=max_log_entries)
        self._worker_task: Optional[asyncio.Task] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stats = {
            "total_crawled": 0,
            "total_chunks": 0,
            "total_entities": 0,
            "failed_count": 0,
            "filtered_count": 0,
        }

    def _on_watchdog_file(self, file_path: Path) -> None:
        """Callback from Watchdog observer thread."""
        if self.status != CrawlerStatus.RUNNING or not self._loop:
            return

        asyncio.run_coroutine_threadsafe(
            self.submit_file(file_path=file_path, source="local_watchdog"),
            self._loop,
        )

    async def start(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        """Start the background crawler service, watcher, and connectors."""
        if self.status == CrawlerStatus.RUNNING:
            return

        self._loop = loop or asyncio.get_event_loop()
        self.watch_dir.mkdir(parents=True, exist_ok=True)

        for conn in self.connectors:
            try:
                await conn.start()
            except Exception as e:
                logger.warning(f"Failed to start connector {conn.name}: {e}")

        # Start filesystem watchdog observer
        self.watcher.start(self._loop)

        # Start background async tasks
        self._worker_task = asyncio.create_task(self._worker_loop())
        self._poll_task = asyncio.create_task(self._poll_loop())

        self.status = CrawlerStatus.RUNNING
        logger.info(f"CrawlerService started (monitoring {self.watch_dir})")

    async def stop(self) -> None:
        """Gracefully stop background crawler service."""
        if self.status == CrawlerStatus.STOPPED:
            return

        self.status = CrawlerStatus.STOPPED
        self.watcher.stop()

        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None

        for conn in self.connectors:
            try:
                await conn.stop()
            except Exception as e:
                logger.warning(f"Error stopping connector {conn.name}: {e}")

        logger.info("CrawlerService stopped")

    def pause(self) -> None:
        """Pause intake without tearing down connections."""
        self.status = CrawlerStatus.PAUSED
        logger.info("CrawlerService paused")

    def resume(self) -> None:
        """Resume active intake."""
        self.status = CrawlerStatus.RUNNING
        logger.info("CrawlerService resumed")

    async def submit_file(
        self,
        file_path: Path,
        source: str = "manual",
        explicit_schema: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> CrawlerEvent:
        """Queue a file for intake with classification and integrity validation."""
        event = CrawlerEvent(
            filename=file_path.name,
            file_path=str(file_path),
            source=source,
        )

        filter_result = self.filter.evaluate_file(file_path)
        if not filter_result.valid:
            event.status = "filtered"
            event.error_message = filter_result.reason
            self._stats["filtered_count"] += 1
            self._logs.appendleft(event)
            logger.info(f"Crawler filtered file {file_path.name}: {filter_result.reason}")
            return event

        chosen_schema = explicit_schema or filter_result.detected_domain
        event.detected_domain = chosen_schema
        event.confidence = filter_result.confidence
        event.status = "pending"

        self._logs.appendleft(event)
        await self._queue.put((file_path, source, chosen_schema, metadata, event))
        return event

    async def submit_payload(
        self,
        filename: str,
        content: bytes | str,
        source: str = "webhook",
        explicit_schema: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> CrawlerEvent:
        """Save raw payload to incoming staging directory and queue for intake."""
        staging_dir = self.watch_dir / "webhooks"
        staging_dir.mkdir(parents=True, exist_ok=True)
        dest = staging_dir / filename

        if isinstance(content, str):
            dest.write_text(content, encoding="utf-8")
        else:
            dest.write_bytes(content)

        return await self.submit_file(
            file_path=dest,
            source=source,
            explicit_schema=explicit_schema,
            metadata=metadata,
        )

    async def scan_now(self) -> int:
        """Trigger immediate scan across all connectors and drop directories."""
        queued_count = 0

        # Poll all connectors
        for conn in self.connectors:
            try:
                files = await conn.poll()
                for f in files:
                    await self.submit_file(f, source=conn.name)
                    queued_count += 1
            except Exception as e:
                logger.warning(f"Error polling connector {conn.name}: {e}")

        logger.info(f"Manual scan completed: {queued_count} files queued")
        return queued_count

    async def _poll_loop(self) -> None:
        """Periodic background polling loop for non-watchdog connectors."""
        while True:
            try:
                await asyncio.sleep(self.poll_interval)
                if self.status == CrawlerStatus.RUNNING:
                    await self.scan_now()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Unexpected error in crawler poll loop: {e}")

    async def _worker_loop(self) -> None:
        """Worker task processing queued files sequentially."""
        while True:
            try:
                file_path, source, schema_name, meta, event = await self._queue.get()

                if self.status == CrawlerStatus.PAUSED:
                    # Re-queue and wait if paused
                    await asyncio.sleep(1.0)
                    await self._queue.put((file_path, source, schema_name, meta, event))
                    self._queue.task_done()
                    continue

                event.status = "processing"
                start_time = time.monotonic()

                try:
                    pipeline = IngestionPipeline(
                        schema_name=schema_name or "healthtech",
                        gateway=self.gateway,
                        ontology_manager=self.ontology_manager,
                        qdrant_client=self.qdrant_client,
                        neo4j_driver=self.neo4j_driver,
                    )

                    result = await pipeline.ingest_file(file_path=file_path, metadata=meta)

                    duration = (time.monotonic() - start_time) * 1000.0
                    event.duration_ms = round(duration, 2)
                    event.chunks_created = result.chunks_created
                    event.entities_extracted = result.entities_extracted
                    event.relationships_extracted = result.relationships_extracted

                    if result.status == "success":
                        event.status = "success"
                        self._stats["total_crawled"] += 1
                        self._stats["total_chunks"] += result.chunks_created
                        self._stats["total_entities"] += result.entities_extracted
                        # Mark processed in local connector to prevent double-intake
                        self.local_connector.mark_processed(file_path)
                    else:
                        event.status = "failed"
                        event.error_message = "; ".join(result.errors)
                        self._stats["failed_count"] += 1

                except Exception as e:
                    event.status = "failed"
                    event.error_message = str(e)
                    event.duration_ms = round((time.monotonic() - start_time) * 1000.0, 2)
                    self._stats["failed_count"] += 1
                    logger.error(f"Failed to auto-ingest {file_path.name}: {e}")

                finally:
                    self._queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker queue error: {e}")

    def get_status(self) -> dict[str, Any]:
        """Return comprehensive status of the crawler engine."""
        return {
            "status": self.status.value,
            "watch_dir": str(self.watch_dir),
            "queue_size": self._queue.qsize(),
            "connectors": [c.get_status() for c in self.connectors],
            "stats": self._stats,
            "recent_activity_count": len(self._logs),
        }

    def get_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent crawler activity log entries."""
        return [item.to_dict() for item in list(self._logs)[:limit]]
