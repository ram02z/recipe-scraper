from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    database_url: str
    api_version: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ["DATABASE_URL"],
            api_version=os.environ["API_VERSION"],
        )
