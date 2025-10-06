"""Client helpers for talking to IMAP and POP3 servers."""
from __future__ import annotations

import imaplib
import logging
import poplib
import ssl
from contextlib import contextmanager
from typing import Generator

from .config import DestinationConfig, SourceConfig

LOGGER = logging.getLogger(__name__)


def _create_ssl_context(verify: bool = True) -> ssl.SSLContext:
    context = ssl.create_default_context()
    if not verify:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


@contextmanager
def imap_connection(config: SourceConfig | DestinationConfig) -> Generator[imaplib.IMAP4, None, None]:
    """Yield a connected IMAP client based on the provided configuration."""

    ssl_context = _create_ssl_context()

    if config.encryption == "ssl":
        client: imaplib.IMAP4 = imaplib.IMAP4_SSL(config.host, config.port, ssl_context=ssl_context)
    else:
        client = imaplib.IMAP4(config.host, config.port)
        if config.encryption == "starttls":
            typ, _ = client.starttls(ssl_context)
            if typ != "OK":
                raise ConnectionError("Failed to initialise STARTTLS for IMAP connection")

    try:
        typ, _ = client.login(config.username, config.password)
        if typ != "OK":
            raise ConnectionError("IMAP login failed")
        yield client
    finally:
        try:
            client.logout()
        except Exception:  # pragma: no cover - cleanup best effort
            LOGGER.debug("Failed to log out from IMAP server", exc_info=True)


@contextmanager
def pop3_connection(config: SourceConfig) -> Generator[poplib.POP3, None, None]:
    """Yield a connected POP3 client based on the provided configuration."""

    ssl_context = _create_ssl_context()

    if config.encryption == "ssl":
        client: poplib.POP3 = poplib.POP3_SSL(config.host, config.port, context=ssl_context)
    else:
        client = poplib.POP3(config.host, config.port)
        if config.encryption == "starttls":
            resp = client.stls(context=ssl_context)
            if b"OK" not in resp.upper():
                raise ConnectionError("Failed to initialise STLS for POP3 connection")

    try:
        client.user(config.username)
        client.pass_(config.password)
        yield client
        client.quit()
    except Exception:
        try:  # pragma: no cover - best effort cleanup
            client.rset()
            client.quit()
        except Exception:
            LOGGER.debug("Failed to reset POP3 session during cleanup", exc_info=True)
        raise

