from dataclasses import dataclass
import os
from pathlib import Path


_API_VERSION_FILE = Path(__file__).with_name("_api_version.txt")


@dataclass(frozen=True)
class Settings:
    database_url: str
    api_version: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ["DATABASE_URL"],
            api_version=os.environ.get("API_VERSION")
            or _API_VERSION_FILE.read_text(encoding="utf-8").strip(),
        )
