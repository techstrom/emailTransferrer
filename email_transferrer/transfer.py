"""Core transfer logic for moving emails between servers."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import List

import imaplib

from .clients import imap_connection, pop3_connection
from .config import AppConfig, SourceConfig
from .state import StateStore

LOGGER = logging.getLogger(__name__)


@dataclass
class TransferResult:
    source: str
    transferred: int
    deleted: int


class EmailTransferrer:
    """Moves messages from configured source servers to their destinations."""

    def __init__(self, config: AppConfig, state: StateStore) -> None:
        self._config = config
        self._state = state
        self._next_run: dict[str, float] = {source.name: 0.0 for source in config.sources}

    def run_once(self) -> List[TransferResult]:
        """Process every configured source once and return transfer statistics."""
        results: List[TransferResult] = []
        now = time.monotonic()

        for source in self._config.sources:
            if not self._should_process(source, now):
                continue

            try:
                if source.protocol == "imap":
                    result = self._process_imap_source(source)
                else:
                    result = self._process_pop3_source(source)
                results.append(result)
            except Exception:  # pragma: no cover - integration level failures
                LOGGER.exception("Failed to process source '%s'", source.name)
            finally:
                self._schedule_next_run(source)
        return results

    def run_forever(self) -> None:  # pragma: no cover - long running loop
        """Continuously poll configured sources according to the global interval."""
        while True:
            results = self.run_once()
            for result in results:
                LOGGER.info(
                    "Transferred %s messages from %s (deleted %s)",
                    result.transferred,
                    result.source,
                    result.deleted,
                )
            sleep_for = self._time_until_next_run()
            if sleep_for > 0:
                time.sleep(sleep_for)

    def _process_imap_source(self, source: SourceConfig) -> TransferResult:
        LOGGER.info("Processing IMAP source '%s'", source.name)
        processed_uids = []
        deleted_count = 0

        with imap_connection(source) as source_client, imap_connection(source.destination) as dest_client:
            self._ensure_mailbox_selected(source_client, source.folder)
            self._ensure_mailbox_exists(dest_client, source.destination.folder)

            uids = self._search_source_uids(source_client, source.search_criteria)
            LOGGER.debug("Found %d messages matching criteria for %s", len(uids), source.name)

            already_processed = self._state.get_processed_uids(source.name)
            new_uids = [uid for uid in uids if uid not in already_processed]

            LOGGER.debug("%d messages remaining after filtering processed items", len(new_uids))

            for uid in new_uids:
                message_bytes = self._fetch_imap_message(source_client, uid)
                if message_bytes is None:
                    continue

                if self._append_to_destination(dest_client, source.destination.folder, message_bytes):
                    processed_uids.append(uid)
                    if source.delete_after_transfer:
                        if self._mark_message_deleted(source_client, uid):
                            deleted_count += 1
                else:
                    LOGGER.error("Failed to append message %s from %s", uid, source.name)

            if source.delete_after_transfer and deleted_count:
                LOGGER.debug("Expunging deleted messages for source %s", source.name)
                source_client.expunge()

        self._state.record_processed_uids(source.name, processed_uids)
        return TransferResult(source=source.name, transferred=len(processed_uids), deleted=deleted_count)

    def _process_pop3_source(self, source: SourceConfig) -> TransferResult:
        LOGGER.info("Processing POP3 source '%s'", source.name)
        processed_ids: List[str] = []
        deleted_count = 0

        with pop3_connection(source) as source_client, imap_connection(source.destination) as dest_client:
            self._ensure_mailbox_exists(dest_client, source.destination.folder)

            response = source_client.uidl()
            listings = response[1]
            uid_map = {}
            for entry in listings:
                if isinstance(entry, bytes):
                    entry = entry.decode("utf-8")
                parts = entry.split()
                if len(parts) >= 2:
                    uid_map[int(parts[0])] = parts[1]

            already_processed = self._state.get_processed_uids(source.name)

            for number, uid in uid_map.items():
                if uid in already_processed:
                    continue

                resp, lines, _ = source_client.retr(number)
                if isinstance(resp, bytes):
                    status_line = resp.upper()
                else:
                    status_line = str(resp).upper().encode("utf-8")

                if not status_line.startswith(b"+OK"):
                    LOGGER.error("Failed to retrieve message %s from %s", uid, source.name)
                    continue

                message_bytes = b"\r\n".join(lines) + b"\r\n"
                if self._append_to_destination(dest_client, source.destination.folder, message_bytes):
                    processed_ids.append(uid)
                    if source.delete_after_transfer:
                        source_client.dele(number)
                        deleted_count += 1
                else:
                    LOGGER.error("Failed to append POP3 message %s from %s", uid, source.name)

        self._state.record_processed_uids(source.name, processed_ids)
        return TransferResult(source=source.name, transferred=len(processed_ids), deleted=deleted_count)

    @staticmethod
    def _ensure_mailbox_selected(client: imaplib.IMAP4, mailbox: str) -> None:
        typ, _ = client.select(mailbox)
        if typ != "OK":
            raise ConnectionError(f"Unable to select mailbox '{mailbox}'")

    @staticmethod
    def _ensure_mailbox_exists(client: imaplib.IMAP4, mailbox: str) -> None:
        typ, _ = client.select(mailbox)
        if typ == "OK":
            return

        typ, data = client.create(mailbox)
        if typ != "OK":
            message = "".join(item.decode("utf-8", "ignore") if isinstance(item, bytes) else str(item) for item in (data or []))
            if "ALREADYEXISTS" not in message.upper():
                raise ConnectionError(f"Unable to create mailbox '{mailbox}' on destination server: {message}")

        typ, _ = client.select(mailbox)
        if typ != "OK":
            raise ConnectionError(f"Unable to select mailbox '{mailbox}' after creation")

    @staticmethod
    def _search_source_uids(client: imaplib.IMAP4, criteria: str) -> List[str]:
        typ, data = client.uid("SEARCH", None, criteria)
        if typ != "OK":
            raise ConnectionError("Failed to search for messages on IMAP source")
        if not data or not data[0]:
            return []
        if isinstance(data[0], bytes):
            items = data[0].split()
        else:
            items = data[0].encode("utf-8").split()
        return [item.decode("utf-8") if isinstance(item, bytes) else item for item in items]

    @staticmethod
    def _fetch_imap_message(client: imaplib.IMAP4, uid: str) -> bytes | None:
        typ, data = client.uid("FETCH", uid, "(RFC822)")
        if typ != "OK" or not data or data[0] is None:
            LOGGER.error("Failed to fetch message UID %s", uid)
            return None
        payload = data[0][1]
        if not isinstance(payload, (bytes, bytearray)):
            LOGGER.error("Unexpected payload type for message %s", uid)
            return None
        return bytes(payload)

    @staticmethod
    def _append_to_destination(client: imaplib.IMAP4, mailbox: str, message: bytes) -> bool:
        typ, _ = client.append(mailbox, None, None, message)
        return typ == "OK"

    @staticmethod
    def _mark_message_deleted(client: imaplib.IMAP4, uid: str) -> bool:
        typ, _ = client.uid("STORE", uid, "+FLAGS", "(\\Deleted)")
        if typ != "OK":
            LOGGER.error("Failed to mark message %s for deletion", uid)
            return False
        return True

    def _get_interval_for_source(self, source: SourceConfig) -> int:
        return source.poll_interval or self._config.poll_interval_seconds

    def _should_process(self, source: SourceConfig, now: float) -> bool:
        next_run = self._next_run.get(source.name, 0.0)
        return now >= next_run

    def _schedule_next_run(self, source: SourceConfig) -> None:
        interval = self._get_interval_for_source(source)
        self._next_run[source.name] = time.monotonic() + interval

    def _time_until_next_run(self) -> float:
        if not self._next_run:
            return float(self._config.poll_interval_seconds)

        now = time.monotonic()
        waits = [max(0.0, next_run - now) for next_run in self._next_run.values()]
        if not waits:
            return float(self._config.poll_interval_seconds)
        return min(waits)


def create_transferrer(config: AppConfig) -> EmailTransferrer:
    """Helper to instantiate an :class:`EmailTransferrer` with its state store."""

    state_store = StateStore(config.state_file)
    return EmailTransferrer(config, state_store)

