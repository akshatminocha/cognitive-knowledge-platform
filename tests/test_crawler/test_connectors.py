"""
Unit tests for Crawler Storage Connectors (Local, GCS, SFTP, S3, Azure).
"""

from pathlib import Path
import pytest

from backend.crawler.connectors import (
    LocalWatchdogConnector,
    GCSStorageConnector,
    SFTPStorageConnector,
    S3StorageConnector,
    AzureBlobStorageConnector,
)


@pytest.mark.asyncio
async def test_local_watchdog_connector(tmp_path: Path):
    watch_dir = tmp_path / "incoming"
    connector = LocalWatchdogConnector(watch_dir=watch_dir)
    await connector.start()
    assert connector.get_status()["running"] is True

    # Initially empty
    files = await connector.poll()
    assert len(files) == 0

    # Add a file
    file1 = watch_dir / "sample1.txt"
    file1.write_text("Hello from local drop")

    polled = await connector.poll()
    assert len(polled) == 1
    assert polled[0].name == "sample1.txt"

    # Second poll should return empty (already processed)
    polled2 = await connector.poll()
    assert len(polled2) == 0

    await connector.stop()
    assert connector.get_status()["running"] is False


@pytest.mark.asyncio
async def test_gcs_storage_connector(tmp_path: Path):
    staging = tmp_path / "gcs_stage"
    connector = GCSStorageConnector(local_staging_dir=staging, bucket_name="test-bucket")
    await connector.start()

    # Add mock blob
    connector.add_mock_blob("telemetry/metrics.json", b'{"cpu": 85}')
    polled = await connector.poll()
    assert len(polled) == 1
    assert polled[0].name == "metrics.json"
    assert polled[0].exists()

    # Second poll should deduplicate
    polled2 = await connector.poll()
    assert len(polled2) == 0

    status = connector.get_status()
    assert status["processed_count"] == 1
    await connector.stop()


@pytest.mark.asyncio
async def test_sftp_storage_connector(tmp_path: Path):
    staging = tmp_path / "sftp_stage"
    connector = SFTPStorageConnector(local_staging_dir=staging)
    await connector.start()

    connector.add_mock_file("bank_transactions.csv", b"id,amount\n1,100")
    polled = await connector.poll()
    assert len(polled) == 1
    assert polled[0].name == "bank_transactions.csv"

    # Second poll
    polled2 = await connector.poll()
    assert len(polled2) == 0
    await connector.stop()


@pytest.mark.asyncio
async def test_s3_storage_connector(tmp_path: Path):
    staging = tmp_path / "s3_stage"
    connector = S3StorageConnector(local_staging_dir=staging)
    await connector.start()

    connector.add_mock_object("incoming/patient_data.pdf", b"%PDF-1.4 mock")
    polled = await connector.poll()
    assert len(polled) == 1
    assert polled[0].name == "patient_data.pdf"
    await connector.stop()


@pytest.mark.asyncio
async def test_azure_storage_connector(tmp_path: Path):
    staging = tmp_path / "azure_stage"
    connector = AzureBlobStorageConnector(local_staging_dir=staging)
    await connector.start()

    connector.add_mock_blob("incoming/invoice.csv", b"inv_id,total\n1001,450.0")
    polled = await connector.poll()
    assert len(polled) == 1
    assert polled[0].name == "invoice.csv"
    await connector.stop()
