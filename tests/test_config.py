import json
from pathlib import Path

from email_transferrer.config import AppConfig, load_config


def test_load_config(tmp_path):
    config_path = tmp_path / "config.json"
    data = {
        "poll_interval_seconds": 120,
        "state_file": "state/data.json",
        "log_level": "debug",
        "sources": [
            {
                "name": "Test",
                "protocol": "imap",
                "host": "imap.test",
                "port": 993,
                "username": "user",
                "password": "pass",
                "destination": {
                    "host": "imap.dest",
                    "port": 993,
                    "username": "dest",
                    "password": "dest-pass",
                },
            }
        ],
    }
    with config_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle)

    config = load_config(config_path)
    assert isinstance(config, AppConfig)
    assert config.poll_interval_seconds == 120
    assert config.state_file == (config_path.parent / "state/data.json").resolve()
    assert config.sources[0].destination.folder == "INBOX"
    assert config.sources[0].encryption == "ssl"


