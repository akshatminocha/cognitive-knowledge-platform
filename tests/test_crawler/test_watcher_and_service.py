"""
Unit tests for DirectoryWatcher and CrawlerService.
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest

from backend.crawler.watcher import DirectoryWatcher
from backend.crawler.service import CrawlerService, CrawlerStatus
from backend.ingestion.pipeline import IngestionResult


@pytest.mark.asyncio
async def test_directory_watcher_lifecycle(tmp_path: Path):
    watch_dir = tmp_path / "incoming"
    detected = []

    def on_ready(p: Path):
        detected.append(p)

    watcher = DirectoryWatcher(watch_dir=watch_dir, on_file_ready=on_ready, debounce_seconds=0.1)
    loop = asyncio.get_event_loop()
    watcher.start(loop)
    assert watcher.is_running is True

    watcher.stop()
    assert watcher.is_running is False


@pytest.mark.asyncio
async def test_crawler_service_lifecycle_and_pause(tmp_path: Path):
    watch_dir = tmp_path / "incoming"
    service = CrawlerService(watch_dir=watch_dir, poll_interval_seconds=100.0)

    loop = asyncio.get_event_loop()
    await service.start(loop)
    assert service.status == CrawlerStatus.RUNNING

    service.pause()
    assert service.status == CrawlerStatus.PAUSED

    service.resume()
    assert service.status == CrawlerStatus.RUNNING

    await service.stop()
    assert service.status == CrawlerStatus.STOPPED


@pytest.mark.asyncio
async def test_crawler_service_submit_and_filter(tmp_path: Path):
    watch_dir = tmp_path / "incoming"
    watch_dir.mkdir(parents=True, exist_ok=True)
    service = CrawlerService(watch_dir=watch_dir)

    # 1. Non-existent file -> filtered
    event = await service.submit_file(watch_dir / "ghost.txt")
    assert event.status == "filtered"
    assert "does not exist" in (event.error_message or "")

    # 2. Valid healthtech file
    doc = watch_dir / "ehr_note.txt"
    doc.write_text("Patient clinical trial notes oncology dosage treatment.")
    event2 = await service.submit_file(doc)
    assert event2.status == "pending"
    assert event2.detected_domain == "healthtech"

    # Status check
    status = service.get_status()
    assert status["queue_size"] == 1
    assert len(service.get_logs()) == 2


@pytest.mark.asyncio
async def test_crawler_service_submit_payload(tmp_path: Path):
    watch_dir = tmp_path / "incoming"
    service = CrawlerService(watch_dir=watch_dir)

    event = await service.submit_payload(
        filename="webhook_invoice.json",
        content='{"transaction_id": "TX-99", "amount": 540.0, "ledger": "debit"}',
        source="webhook",
    )
    assert event.status == "pending"
    assert event.detected_domain == "fintech"
    assert (watch_dir / "webhooks" / "webhook_invoice.json").exists()


@pytest.mark.asyncio
async def test_crawler_service_worker_execution(tmp_path: Path):
    watch_dir = tmp_path / "incoming"
    service = CrawlerService(watch_dir=watch_dir, poll_interval_seconds=100.0)

    loop = asyncio.get_event_loop()
    await service.start(loop)

    doc = watch_dir / "clinical_summary.txt"
    doc.write_text("Patient diagnosed with cardiology hypertension.")

    # Mock IngestionPipeline.ingest_file
    mock_result = IngestionResult(
        filename="clinical_summary.txt",
        file_type="txt",
        status="success",
        chunks_created=3,
        entities_extracted=5,
        relationships_extracted=4,
    )

    with patch("backend.crawler.service.IngestionPipeline.ingest_file", new_callable=AsyncMock) as mock_ingest:
        mock_ingest.return_value = mock_result
        event = await service.submit_file(doc)

        # Wait for queue worker to process
        await asyncio.sleep(0.3)

        assert event.status == "success"
        assert event.chunks_created == 3
        assert event.entities_extracted == 5
        assert service._stats["total_crawled"] == 1

    await service.stop()
