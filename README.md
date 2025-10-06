# emailTransferrer

Transfer emails from POP3/IMAP servers into a destination IMAP mailbox based on a YAML configuration file.

## Features

- Supports POP3 and IMAP source servers with SSL or STARTTLS encryption
- Stores processed message identifiers locally to avoid duplicate transfers
- Optionally deletes source messages after they are safely appended to the destination mailbox
- Allows per-source configuration of destination folders

## Getting started

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Copy the sample configuration and edit it with your server credentials:

   ```bash
   cp config.example.yaml config.yaml
   ```

   > **Tip:** If you cannot install [PyYAML](https://pyyaml.org/), you can also provide the configuration as JSON and
   > point the `--config` option to that `.json` file.

3. Run a single transfer cycle:

   ```bash
   python main.py --config config.yaml --once
   ```

   Omit `--once` to keep the process running and polling according to `poll_interval_seconds`.

## Configuration

See `config.example.yaml` for a fully documented example. Each source defines the connection details for the mailbox to read from and the IMAP destination to append messages to. Fields include:

- `protocol`: `imap` or `pop3`
- `host` / `port`
- `encryption`: `ssl`, `starttls`, or `none`
- `username` / `password`
- `folder` (IMAP only) and optional `search_criteria`
- `delete_after_transfer`: delete the source message after a successful append
- `destination`: nested destination IMAP credentials and folder name

The application stores its progress in the configured `state_file` to avoid re-transferring messages that have already been handled.

