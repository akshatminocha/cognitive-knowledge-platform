"""
Autonomous Data Crawler Package.

Proactive 24/7 background ingestion service monitoring drop folders,
cloud storage buckets (GCS/S3/Azure), and SFTP drop points.
"""

from backend.crawler.filter import DomainFilter, FileIntegrityGate, FilterResult
from backend.crawler.connectors import (
    BaseStorageConnector,
    LocalWatchdogConnector,
    GCSStorageConnector,
    SFTPStorageConnector,
    S3StorageConnector,
    AzureBlobStorageConnector,
)
from backend.crawler.watcher import DirectoryWatcher
from backend.crawler.service import CrawlerService, CrawlerEvent, CrawlerStatus

__all__ = [
    "DomainFilter",
    "FileIntegrityGate",
    "FilterResult",
    "BaseStorageConnector",
    "LocalWatchdogConnector",
    "GCSStorageConnector",
    "SFTPStorageConnector",
    "S3StorageConnector",
    "AzureBlobStorageConnector",
    "DirectoryWatcher",
    "CrawlerService",
    "CrawlerEvent",
    "CrawlerStatus",
]
