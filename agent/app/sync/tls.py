"""The trusted certificates for every HTTPS / WSS connection the agent makes.

The packaged agent ships its own list (certifi). If that file is missing (a half-finished uninstall, an antivirus
quarantine) or another program set ``SSL_CERT_FILE`` to a file that no longer exists, building the usual context
raises FileNotFoundError and the agent could not start at all. Instead we fall back to Windows' own trusted
certificates, so the agent keeps working and never crashes on start-up over this.
"""

from __future__ import annotations

import functools
import logging
import os
import ssl

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1)
def tls_context() -> ssl.SSLContext:
    """Bundled certificates when present, otherwise the operating system's. Ignores a broken SSL_CERT_FILE."""
    try:
        import certifi

        bundle = certifi.where()
        if os.path.isfile(bundle):
            return ssl.create_default_context(cafile=bundle)
        logger.warning("Bundled certificate list is missing (%s); using the system's certificates", bundle)
    except (ImportError, OSError, ssl.SSLError):
        logger.warning("Bundled certificate list unusable; using the system's certificates", exc_info=True)
    try:
        # Loads Windows' trusted root store; a missing SSL_CERT_FILE / SSL_CERT_DIR is skipped, not fatal.
        return ssl.create_default_context()
    except (OSError, ssl.SSLError):
        logger.warning("System certificates unavailable; starting with an empty trust list", exc_info=True)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)  # still verifies: connections fail safely, no crash
        return context
