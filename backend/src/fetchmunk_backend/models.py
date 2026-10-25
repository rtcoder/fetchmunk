from dataclasses import dataclass, asdict, field
from pathlib import Path


@dataclass
class WorkerRequest:
    job_id: str
    attempt: int
    url: str
    output_dir: Path
    archive_path: Path
    credentials: dict | None = field(default=None, repr=False)
    engine: str = "gallery-dl"
    credential_path: str | None = None


@dataclass
class WorkerEvent:
    kind: str
    data: dict


@dataclass
class WorkerResult:
    downloaded: int = 0
    skipped: int = 0
    failed_files: int = 0
    error_code: str | None = None
