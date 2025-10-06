"""Configuration loading for the email transferrer application."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

try:  # pragma: no cover - optional dependency
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - handled at runtime
    yaml = None  # type: ignore[assignment]

EncryptionMode = Literal["ssl", "starttls", "none"]
Protocol = Literal["imap", "pop3"]


def _normalise_encryption(value: Optional[str]) -> EncryptionMode:
    if not value:
        return "ssl"
    value = value.lower()
    if value not in {"ssl", "starttls", "none"}:
        raise ValueError(f"Unsupported encryption mode: {value}")
    return value  # type: ignore[return-value]


def _normalise_protocol(value: str) -> Protocol:
    value = value.lower()
    if value not in {"imap", "pop3"}:
        raise ValueError(f"Unsupported protocol: {value}")
    return value  # type: ignore[return-value]


@dataclass
class DestinationConfig:
    """Configuration for a destination IMAP server."""

    host: str
    port: int
    username: str
    password: str
    folder: str = "INBOX"
    encryption: EncryptionMode = "ssl"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DestinationConfig":
        try:
            host = data["host"]
            port = int(data.get("port", 993))
            username = data["username"]
            password = data["password"]
        except KeyError as exc:  # pragma: no cover - defensive programming
            raise ValueError(f"Missing destination configuration field: {exc.args[0]}") from exc

        folder = data.get("folder") or "INBOX"
        encryption = _normalise_encryption(data.get("encryption"))
        return cls(host=host, port=port, username=username, password=password, folder=folder, encryption=encryption)


@dataclass
class SourceConfig:
    """Configuration for a source email server."""

    name: str
    protocol: Protocol
    host: str
    port: int
    username: str
    password: str
    destination: DestinationConfig
    encryption: EncryptionMode = "ssl"
    folder: str = "INBOX"
    search_criteria: str = "UNSEEN"
    delete_after_transfer: bool = False
    poll_interval: Optional[int] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SourceConfig":
        try:
            name = data["name"]
            protocol = _normalise_protocol(data["protocol"])
            host = data["host"]
            port = int(data.get("port", 993 if protocol == "imap" else 995))
            username = data["username"]
            password = data["password"]
            destination_raw = data["destination"]
        except KeyError as exc:
            raise ValueError(f"Missing source configuration field: {exc.args[0]}") from exc

        destination = DestinationConfig.from_dict(destination_raw)
        folder = data.get("folder") or "INBOX"
        search_criteria = data.get("search_criteria") or "UNSEEN"
        delete_after_transfer = bool(data.get("delete_after_transfer", False))
        encryption = _normalise_encryption(data.get("encryption"))
        poll_interval = data.get("poll_interval")
        if poll_interval is not None:
            poll_interval = int(poll_interval)
            if poll_interval <= 0:
                raise ValueError("poll_interval must be a positive integer")

        return cls(
            name=name,
            protocol=protocol,
            host=host,
            port=port,
            username=username,
            password=password,
            encryption=encryption,
            folder=folder,
            search_criteria=search_criteria,
            delete_after_transfer=delete_after_transfer,
            destination=destination,
            poll_interval=poll_interval,
        )


@dataclass
class AppConfig:
    """Top level configuration object."""

    sources: List[SourceConfig]
    poll_interval_seconds: int = 300
    state_file: Path = Path("state.json")
    log_level: str = "INFO"

    @classmethod
    def from_dict(cls, data: Dict[str, Any], *, base_path: Path) -> "AppConfig":
        sources_raw = data.get("sources") or []
        if not sources_raw:
            raise ValueError("At least one source must be defined in configuration")

        sources = [SourceConfig.from_dict(item) for item in sources_raw]

        poll_interval_seconds = int(data.get("poll_interval_seconds", 300))
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")

        state_file_raw = data.get("state_file", "state.json")
        state_file = (base_path / state_file_raw).expanduser().resolve()
        log_level = (data.get("log_level") or "INFO").upper()

        return cls(
            sources=sources,
            poll_interval_seconds=poll_interval_seconds,
            state_file=state_file,
            log_level=log_level,
        )


def _load_raw_configuration(config_path: Path) -> Dict[str, Any]:
    text = config_path.read_text(encoding="utf-8")
    suffix = config_path.suffix.lower()

    if suffix in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError(
                "PyYAML is required to parse YAML configuration files. Install PyYAML or use JSON instead."
            )
        raw = yaml.safe_load(text) or {}
    elif suffix == ".json":
        raw = json.loads(text or "{}")
    else:
        if yaml is not None:
            raw = yaml.safe_load(text) or {}
        else:
            raw = json.loads(text or "{}")

    if not isinstance(raw, dict):
        raise ValueError("Configuration file must define a dictionary at the top level")
    return raw


def load_config(path: Path | str) -> AppConfig:
    """Load the application configuration from the provided path."""

    config_path = Path(path).expanduser().resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    raw = _load_raw_configuration(config_path)
    return AppConfig.from_dict(raw, base_path=config_path.parent)

