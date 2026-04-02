"""Inițializarea integrării MyENGIE România (Engie Romania).

Arhitectura: UN SINGUR coordinator per config_entry (per utilizator).
POC-based: un utilizator poate avea mai multe locuri de consum (POC-uri).
Licențiere: conform STANDARD-LICENTA.md v3.3 — server-side, Ed25519, grace period.
"""

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import DOMAIN, DEFAULT_UPDATE_INTERVAL, DOMAIN_TOKEN_STORE, LICENSE_DATA_KEY, PLATFORMS
from .api import MyEngieApiClient
from .coordinator import MyEngieCoordinator
from .license import LicenseManager

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class MyEngieRuntimeData:
    """Structură tipizată pentru datele runtime ale integrării."""

    coordinator: MyEngieCoordinator | None = None
    api_client: MyEngieApiClient | None = None


async def async_setup(hass: HomeAssistant, config: dict):
    """Configurează integrarea globală MyENGIE România."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Configurează integrarea pentru o anumită intrare (config entry)."""
    _LOGGER.info("Se configurează integrarea %s (entry_id=%s).", DOMAIN, entry.entry_id)

    hass.data.setdefault(DOMAIN, {})

    # ══════════════════════════════════════════════
    # Inițializare License Manager (o singură instanță per domeniu)
    # Conform STANDARD-LICENTA.md §3.5
    # ══════════════════════════════════════════════
    if LICENSE_DATA_KEY not in hass.data.get(DOMAIN, {}):
        _LOGGER.debug("[MyENGIE] Inițializez LicenseManager (prima entry)")
        license_mgr = LicenseManager(hass)
        await license_mgr.async_load()
        hass.data[DOMAIN][LICENSE_DATA_KEY] = license_mgr
        _LOGGER.debug(
            "[MyENGIE] LicenseManager: status=%s, valid=%s, fingerprint=%s...",
            license_mgr.status,
            license_mgr.is_valid,
            license_mgr.fingerprint[:16],
        )

        # ── Heartbeat periodic — intervalul vine de la server (via valid_until) ──
        from datetime import timedelta

        from homeassistant.helpers.event import (
            async_track_point_in_time,
            async_track_time_interval,
        )
        from homeassistant.util import dt as dt_util

        interval_sec = license_mgr.check_interval_seconds
        _LOGGER.debug(
            "[MyENGIE] Programez heartbeat periodic la fiecare %d secunde (%d ore)",
            interval_sec,
            interval_sec // 3600,
        )

        async def _heartbeat_periodic(_now) -> None:
            """Verifică statusul la server dacă cache-ul a expirat."""
            mgr: LicenseManager | None = hass.data.get(DOMAIN, {}).get(
                LICENSE_DATA_KEY
            )
            if not mgr:
                _LOGGER.debug("[MyENGIE] Heartbeat: LicenseManager nu există, skip")
                return
            if mgr.needs_heartbeat:
                _LOGGER.debug("[MyENGIE] Heartbeat: cache expirat, verific la server")
                await mgr.async_heartbeat()
            else:
                _LOGGER.debug("[MyENGIE] Heartbeat: cache valid, nu e nevoie de verificare")

        cancel_heartbeat = async_track_time_interval(
            hass,
            _heartbeat_periodic,
            timedelta(seconds=interval_sec),
        )
        hass.data[DOMAIN]["_cancel_heartbeat"] = cancel_heartbeat
        _LOGGER.debug("[MyENGIE] Heartbeat programat și stocat în hass.data")

        # ── Timer precis la valid_until (zero gap la expirare cache) ──
        # Conform STANDARD-LICENTA.md §3.5 / §6.2
        def _schedule_cache_expiry_check(mgr_ref: LicenseManager) -> None:
            """Programează un check EXACT la momentul expirării cache-ului."""
            # Anulează timer-ul anterior (dacă există)
            cancel_prev = hass.data.get(DOMAIN, {}).pop(
                "_cancel_cache_expiry", None
            )
            if cancel_prev:
                cancel_prev()

            valid_until = (mgr_ref._status_token or {}).get("valid_until")
            if not valid_until or valid_until <= 0:
                return

            expiry_dt = dt_util.utc_from_timestamp(valid_until)
            # Adaugă 2 secunde ca marjă (evită race condition cu cache check)
            expiry_dt = expiry_dt + timedelta(seconds=2)

            async def _on_cache_expiry(_now) -> None:
                """Callback executat EXACT la expirarea cache-ului."""
                mgr_now: LicenseManager | None = hass.data.get(
                    DOMAIN, {}
                ).get(LICENSE_DATA_KEY)
                if not mgr_now:
                    return

                was_valid = mgr_now.is_valid
                _LOGGER.debug(
                    "[MyENGIE] Cache expirat — verific imediat la server"
                )
                await mgr_now.async_check_status()
                now_valid = mgr_now.is_valid

                if was_valid != now_valid:
                    if now_valid:
                        _LOGGER.info(
                            "[MyENGIE] Licența a redevenit validă — reîncarc"
                        )
                    else:
                        _LOGGER.warning(
                            "[MyENGIE] Licența a devenit invalidă — reîncarc"
                        )
                    await mgr_now._async_reload_entries()

                # Programează următorul check (dacă serverul a dat valid_until nou)
                _schedule_cache_expiry_check(mgr_now)

            cancel_expiry = async_track_point_in_time(
                hass, _on_cache_expiry, expiry_dt
            )
            hass.data[DOMAIN]["_cancel_cache_expiry"] = cancel_expiry

            _LOGGER.debug(
                "[MyENGIE] Cache expiry timer programat la %s",
                expiry_dt.isoformat(),
            )

        _schedule_cache_expiry_check(license_mgr)

        # ── Notificare re-enable (dacă a fost dezactivată anterior) ──
        was_disabled = hass.data.pop(f"{DOMAIN}_was_disabled", False)
        if was_disabled:
            await license_mgr.async_notify_event("integration_enabled")

        if not license_mgr.is_valid:
            _LOGGER.warning(
                "[MyENGIE] Integrarea nu are licență validă. "
                "Senzorii vor afișa 'Licență necesară'."
            )
        elif license_mgr.is_trial_valid:
            _LOGGER.info(
                "[MyENGIE] Perioadă de evaluare — %d zile rămase",
                license_mgr.trial_days_remaining,
            )
        else:
            _LOGGER.info(
                "[MyENGIE] Licență activă — tip: %s",
                license_mgr.license_type,
            )
    else:
        _LOGGER.debug(
            "[MyENGIE] LicenseManager există deja (entry suplimentară)"
        )

    # ══════════════════════════════════════════════
    # Client API + Coordinator (un singur per utilizator)
    # ══════════════════════════════════════════════

    session = async_get_clientsession(hass)
    username = entry.data["username"]
    password = entry.data["password"]
    update_interval = entry.data.get("update_interval", DEFAULT_UPDATE_INTERVAL)

    # Un singur client API (un singur utilizator, un singur token)
    api_client = MyEngieApiClient(session, username, password)

    # Injectăm token-ul salvat — prioritate: hass.data (proaspăt, de la config_flow),
    # apoi config_entry.data (persistent, pentru restart HA)
    token_store = hass.data.get(DOMAIN_TOKEN_STORE, {})
    stored_token = token_store.pop(username.lower(), None)
    if stored_token:
        api_client.inject_token(stored_token)
        _LOGGER.debug(
            "Token injectat din config_flow (proaspăt) pentru %s.",
            username,
        )
    elif entry.data.get("token_data"):
        api_client.inject_token(entry.data["token_data"])
        _LOGGER.debug(
            "Token injectat din config_entry.data (persistent) pentru %s.",
            username,
        )
    else:
        _LOGGER.debug(
            "Niciun token salvat disponibil pentru %s. Se va face login.",
            username,
        )
    # Curățăm store-ul dacă e gol
    if DOMAIN_TOKEN_STORE in hass.data and not hass.data[DOMAIN_TOKEN_STORE]:
        hass.data.pop(DOMAIN_TOKEN_STORE, None)

    # Un singur coordinator per utilizator
    coordinator = MyEngieCoordinator(
        hass,
        api_client=api_client,
        config_entry=entry,
        update_interval=update_interval,
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except UpdateFailed as err:
        _LOGGER.error(
            "Prima actualizare eșuată (entry_id=%s): %s",
            entry.entry_id, err,
        )
        return False
    except Exception as err:
        _LOGGER.exception(
            "Eroare neașteptată la prima actualizare (entry_id=%s): %s",
            entry.entry_id, err,
        )
        return False

    # Salvăm datele runtime
    entry.runtime_data = MyEngieRuntimeData(
        coordinator=coordinator,
        api_client=api_client,
    )

    # ── Încărcăm platformele NECONDIȚIONAT (gating-ul e în sensor.py) ──
    # Conform STANDARD-LICENTA.md §3.5
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Listener pentru modificarea opțiunilor
    entry.async_on_unload(entry.add_update_listener(_async_update_options))

    _LOGGER.info(
        "Integrarea %s configurată (entry_id=%s).",
        DOMAIN, entry.entry_id,
    )
    return True


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry):
    """Reîncarcă integrarea când opțiunile se schimbă."""
    _LOGGER.info(
        "Opțiunile integrării %s s-au schimbat (entry_id=%s). Se reîncarcă...",
        DOMAIN, entry.entry_id,
    )
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Descărcarea intrării din config_entries."""
    _LOGGER.info(
        "[MyENGIE] ── async_unload_entry ── entry_id=%s",
        entry.entry_id,
    )

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    _LOGGER.debug("[MyENGIE] Unload platforme: %s", "OK" if unload_ok else "EȘUAT")

    if unload_ok:
        # runtime_data se curăță automat de HA la unload — nu facem pop manual

        # Verifică dacă mai sunt entry-uri active
        remaining_entries = hass.config_entries.async_entries(DOMAIN)
        entry_ids_ramase = {e.entry_id for e in remaining_entries if e.entry_id != entry.entry_id}

        _LOGGER.debug(
            "[MyENGIE] Entry-uri rămase după unload: %d (%s)",
            len(entry_ids_ramase),
            entry_ids_ramase or "niciuna",
        )

        if not entry_ids_ramase:
            _LOGGER.info("[MyENGIE] Ultima entry descărcată — curăț domeniul complet")

            # ── Notificare lifecycle (înainte de cleanup!) ──
            mgr = hass.data[DOMAIN].get(LICENSE_DATA_KEY)
            if mgr and not hass.is_stopping:
                if entry.disabled_by:
                    await mgr.async_notify_event("integration_disabled")
                    hass.data[f"{DOMAIN}_was_disabled"] = True
                else:
                    hass.data.setdefault(f"{DOMAIN}_notify", {}).update({
                        "fingerprint": mgr.fingerprint,
                        "license_key": mgr._data.get("license_key", ""),
                    })
                    _LOGGER.debug(
                        "[MyENGIE] Fingerprint salvat pentru async_remove_entry"
                    )

            # Oprește heartbeat-ul periodic
            cancel_hb = hass.data[DOMAIN].pop("_cancel_heartbeat", None)
            if cancel_hb:
                cancel_hb()
                _LOGGER.debug("[MyENGIE] Heartbeat periodic oprit")

            # Oprește timer-ul de cache expiry
            cancel_ce = hass.data[DOMAIN].pop("_cancel_cache_expiry", None)
            if cancel_ce:
                cancel_ce()
                _LOGGER.debug("[MyENGIE] Cache expiry timer oprit")

            # Elimină LicenseManager
            hass.data[DOMAIN].pop(LICENSE_DATA_KEY, None)
            _LOGGER.debug("[MyENGIE] LicenseManager eliminat")

            # Elimină domeniul complet
            hass.data.pop(DOMAIN, None)
            _LOGGER.debug("[MyENGIE] hass.data[%s] eliminat complet", DOMAIN)

            _LOGGER.info("[MyENGIE] Cleanup complet — domeniul %s descărcat", DOMAIN)
    else:
        _LOGGER.error("[MyENGIE] Unload EȘUAT pentru entry_id=%s", entry.entry_id)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Notifică serverul când integrarea e complet eliminată (ștearsă)."""
    _LOGGER.debug(
        "[MyENGIE] ── async_remove_entry ── entry_id=%s",
        entry.entry_id,
    )

    remaining = hass.config_entries.async_entries(DOMAIN)
    if not remaining:
        notify_data = hass.data.pop(f"{DOMAIN}_notify", None)
        if notify_data and notify_data.get("fingerprint"):
            await _send_lifecycle_event(
                hass,
                notify_data["fingerprint"],
                notify_data.get("license_key", ""),
                "integration_removed",
            )


async def _send_lifecycle_event(
    hass: HomeAssistant, fingerprint: str, license_key: str, action: str
) -> None:
    """Trimite un eveniment lifecycle direct (fără LicenseManager).

    Folosit în async_remove_entry când LicenseManager nu mai există.
    Conform STANDARD-LICENTA.md §3.5 — sesiune partajată, nu aiohttp.ClientSession() nouă.
    """
    import hashlib
    import hmac as hmac_lib
    import json
    import time

    import aiohttp

    from .license import INTEGRATION, LICENSE_API_URL

    timestamp = int(time.time())
    payload = {
        "fingerprint": fingerprint,
        "timestamp": timestamp,
        "action": action,
        "license_key": license_key,
        "integration": INTEGRATION,
    }
    data = {k: v for k, v in payload.items() if k != "hmac"}
    msg = json.dumps(data, sort_keys=True).encode()
    payload["hmac"] = hmac_lib.new(
        fingerprint.encode(), msg, hashlib.sha256
    ).hexdigest()

    try:
        session = async_get_clientsession(hass)
        async with session.post(
            f"{LICENSE_API_URL}/notify",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=10),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "MyEngie-HA-Integration/1.0",
            },
        ) as resp:
            if resp.status == 200:
                result = await resp.json()
                if not result.get("success"):
                    _LOGGER.warning(
                        "[MyENGIE] Server a refuzat '%s': %s",
                        action, result.get("error"),
                    )
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("[MyENGIE] Nu s-a putut raporta '%s': %s", action, err)


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrare de la versiuni vechi la versiunea curentă."""
    _LOGGER.debug(
        "Migrare config entry %s de la versiunea %s.",
        config_entry.entry_id, config_entry.version,
    )

    if config_entry.version < 3:
        # v1/v2 → v3: convertim formatul vechi
        old_data = dict(config_entry.data)
        new_data = {
            "username": old_data.get("username", ""),
            "password": old_data.get("password", ""),
            "update_interval": old_data.get(
                "update_interval",
                config_entry.options.get("update_interval", DEFAULT_UPDATE_INTERVAL),
            ),
        }
        # Păstrează token_data la migrare
        if old_data.get("token_data"):
            new_data["token_data"] = old_data["token_data"]

        _LOGGER.info(
            "Migrare entry %s: v%s → v3.",
            config_entry.entry_id, config_entry.version,
        )

        hass.config_entries.async_update_entry(
            config_entry, data=new_data, options={}, version=3
        )
        return True

    _LOGGER.error(
        "Versiune necunoscută pentru migrare: %s (entry_id=%s).",
        config_entry.version, config_entry.entry_id,
    )
    return False
