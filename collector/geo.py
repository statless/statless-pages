"""In-memory MaxMind GeoIP2 Reader wrapper (zero-disk RAM lookups).

The country database is opened once in ``MODE_MEMORY`` so every lookup
after startup is served from RAM - no per-request disk I/O. Missing DB,
private/reserved IPs, and lookup errors all map to ``"XX"`` (unknown)
instead of raising, so tracking never breaks the pixel response.
"""

from __future__ import annotations

import ipaddress
import logging
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import maxminddb
from geoip2.errors import AddressNotFoundError
from maxminddb import InvalidDatabaseError

if TYPE_CHECKING:
    from geoip2.database import Reader

log = logging.getLogger(__name__)

UNKNOWN = "XX"


class GeoLookup:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._reader: Reader | None = None
        if self.db_path.is_file():
            try:
                import geoip2.database

                self._reader = geoip2.database.Reader(str(self.db_path), mode=maxminddb.MODE_MEMORY)
                log.info("GeoIP2 loaded into RAM from %s", self.db_path)
            except (ImportError, InvalidDatabaseError, OSError) as exc:
                # Corrupt/unreadable DB or missing dependency: tracking must
                # never break on GeoIP failure, so degrade to no country data.
                log.warning("GeoIP2 init failed (%s): country resolution disabled", exc)
        else:
            log.warning("GeoIP2 DB not found at %s: country resolution disabled", self.db_path)

    def country(self, ip: str) -> str:
        """Return ISO 3166-1 alpha-2 country code, or ``"XX"`` when unknown."""
        try:
            parsed = ipaddress.ip_address(ip.strip())
            if parsed.is_private or parsed.is_loopback or parsed.is_multicast or parsed.is_reserved:
                return UNKNOWN
        except ValueError:
            return UNKNOWN
        if self._reader is None:
            return UNKNOWN
        try:
            resp = self._reader.country(ip.strip())
            code = (resp.country.iso_code or "").upper()
            return code if len(code) == 2 else UNKNOWN
        except AddressNotFoundError, InvalidDatabaseError, TypeError, ValueError:
            # Unknown IP (not in DB) or corrupt record maps to "XX", never raises.
            return UNKNOWN
        except OSError:
            # MODE_MEMORY reads from RAM; an I/O error here is unrecoverable -
            # disable lookups rather than break tracking.
            log.warning("GeoIP2 lookup failed; country resolution disabled")
            self.close()
            return UNKNOWN

    def close(self) -> None:
        try:
            if self._reader is not None:
                self._reader.close()
        except OSError:
            pass
        self._reader = None


@lru_cache(maxsize=1)
def get_geo() -> GeoLookup:
    from .config import get_settings

    return GeoLookup(get_settings().geoip_db_path)
