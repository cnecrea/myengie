"""
ConfigFlow și OptionsFlow pentru integrarea MyENGIE România (Engie Romania).

Utilizatorul introduce email + parolă.
Engie nu suportă MFA — pașii MFA sunt stuburi care nu vor fi niciodată atinși.
Licența se gestionează din OptionsFlow (pasul "licenta").
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState, ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN_TOKEN_STORE,
    CONF_LICENSE_KEY,
    LICENSE_DATA_KEY,
    LICENSE_PURCHASE_URL,
)
from . import _signature
from .api import MyEngieApiClient

_LOGGER = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Helper: salvează token-ul în hass.data pentru __init__.py
# ------------------------------------------------------------------

def _store_token(hass, username: str, api: MyEngieApiClient) -> None:
    """Salvează token-ul API în hass.data pentru a fi preluat de __init__.py."""
    token_data = api.export_token_data()
    if token_data is None:
        return
    store = hass.data.setdefault(DOMAIN_TOKEN_STORE, {})
    store[username.lower()] = token_data
    _LOGGER.debug(
        "Token salvat în hass.data pentru %s (token=%s...).",
        username,
        token_data.get("token", "")[:8] if token_data.get("token") else "None",
    )


# ------------------------------------------------------------------
# ConfigFlow
def _update_and_reload(
    hass, entry: config_entries.ConfigEntry, data: dict[str, Any], **kwargs: Any
) -> None:
    """Salvează intrarea și o reîncarcă o singură dată.

    Listener-ul de update reîncarcă singur intrarea când s-a schimbat
    configurația (fără token). Altfel — ex: doar un token nou, sau intrarea
    nu rulează (setup eșuat) — reîncărcăm aici. (Înainte: update + reload
    explicit = două reload-uri.) Decizia se ia ÎNAINTE de update: listener-ul
    pornește imediat.
    """
    runtime = getattr(entry, "runtime_data", None)
    listener_reloads = (
        entry.state is ConfigEntryState.LOADED
        and runtime is not None
        and getattr(runtime, "config_signature", None) != _signature(data, entry.options)
    )
    hass.config_entries.async_update_entry(entry, data=data, **kwargs)
    if not listener_reloads:
        hass.config_entries.async_schedule_reload(entry.entry_id)


# ------------------------------------------------------------------

class MyEngieConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """ConfigFlow — autentificare MyENGIE România (Engie Romania)."""

    VERSION = 3

    def __init__(self) -> None:
        self._username: str = ""
        self._password: str = ""
        self._update_interval: int = DEFAULT_UPDATE_INTERVAL
        self._api: MyEngieApiClient | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pasul 1: Autentificare."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._username = user_input["username"]
            self._password = user_input["password"]
            self._update_interval = user_input.get(
                "update_interval", DEFAULT_UPDATE_INTERVAL
            )

            await self.async_set_unique_id(self._username.lower())
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            self._api = MyEngieApiClient(session, self._username, self._password)

            login_result = await self._api.async_login()

            if login_result == MyEngieApiClient.LOGIN_OK:
                # Login reușit — salvăm token-ul și creăm entry
                _store_token(self.hass, self._username, self._api)

                return self.async_create_entry(
                    title=f"MyENGIE România ({self._username})",
                    data={
                        "username": self._username,
                        "password": self._password,
                        "update_interval": self._update_interval,
                        "token_data": self._api.export_token_data(),
                    },
                )
            else:
                # login_result e direct cheia de eroare din strings.json
                errors["base"] = login_result

        schema = vol.Schema(
            {
                vol.Required("username"): str,
                vol.Required("password"): str,
                vol.Optional(
                    "update_interval", default=DEFAULT_UPDATE_INTERVAL
                ): vol.All(int, vol.Range(min=3600)),
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    # ─────────────────────────────────────────
    # Reautentificare (parolă schimbată)
    # ─────────────────────────────────────────
    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Pornit de Home Assistant când ENGIE respinge credențialele salvate."""
        self._reauth_username = entry_data["username"]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Parola nouă → login → salvare + reload."""
        errors: dict[str, str] = {}
        if user_input is not None:
            password = user_input["password"]
            api = MyEngieApiClient(
                async_get_clientsession(self.hass), self._reauth_username, password
            )
            result = await api.async_login()
            if result == MyEngieApiClient.LOGIN_OK:
                entry = self._get_reauth_entry()
                _update_and_reload(
                    self.hass,
                    entry,
                    {**entry.data, "password": password, "token_data": api.export_token_data()},
                )
                return self.async_abort(reason="reauth_successful")
            errors["base"] = result

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required("password"): str}),
            errors=errors,
            description_placeholders={"username": self._reauth_username},
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> MyEngieOptionsFlow:
        return MyEngieOptionsFlow()


# ------------------------------------------------------------------
# OptionsFlow
# ------------------------------------------------------------------

# ── Textele licenței: aceleași în toate integrările hubinteligent (standardizate pe 12.11.2026) ──

_TIP_LICENTA = {
    # Tipurile emise de WebAPI (LICENSE_DURATION)
    "perpetual": ("permanentă", "permanent"),
    "annual": ("anuală", "annual"),
    "semi_annual": ("semestrială", "semi-annual"),
    "monthly": ("lunară", "monthly"),
}


def _tip_licenta(tip: str | None, is_ro: bool) -> str:
    """Eticheta tipului de licență primit de la server."""
    if not tip:
        return "necunoscut" if is_ro else "unknown"
    ro, en = _TIP_LICENTA.get(tip, (tip, tip))
    return ro if is_ro else en


def _zile_ramase(zile: int, is_ro: bool) -> str:
    """„o zi rămasă”, „5 zile rămase”, „20 de zile rămase” — „1 day left”, „5 days left”."""
    if zile <= 0:
        return "ultima zi" if is_ro else "last day"
    if not is_ro:
        return "1 day left" if zile == 1 else f"{zile} days left"
    if zile == 1:
        return "o zi rămasă"
    return f"{zile} {'de ' if zile % 100 >= 20 or zile % 100 == 0 else ''}zile rămase"


def _status_licenta(mgr, is_ro: bool) -> str:
    """Starea licenței, afișată la pasul „Licență”, deasupra câmpului „Cheie de licență”."""
    from homeassistant.util import dt as dt_util

    def data(moment: float) -> str:
        return dt_util.as_local(dt_util.utc_from_timestamp(moment)).strftime("%d.%m.%Y")

    obtine = f"🛒 {'Obține o licență' if is_ro else 'Get a license'}: {LICENSE_PURCHASE_URL}"
    if mgr.status == "licensed":
        linii = [f"✅ {'Licență activă' if is_ro else 'Active license'} ({_tip_licenta(mgr.license_type, is_ro)})"]
        if mgr.license_key_masked:
            linii[0] += f" — {mgr.license_key_masked}"
        if mgr.activated_at:
            linii.append(f"{'Activată la' if is_ro else 'Activated on'}: {data(mgr.activated_at)}")
        if mgr.license_expires_at:
            linii.append(f"📅 {'Expiră la' if is_ro else 'Expires on'}: {data(mgr.license_expires_at)}")
        else:
            linii.append("Valabilitate: nelimitată" if is_ro else "Validity: unlimited")
        return "\n".join(linii)
    if mgr.status == "trial":
        perioada = "Perioadă de test" if is_ro else "Free trial"
        return "\n".join([f"⏳ {perioada}: {_zile_ramase(mgr.trial_days_remaining, is_ro)}", "", obtine])
    if mgr.status == "expired" and mgr.has_license:
        linii = ["❌ Licență expirată" if is_ro else "❌ License expired"]
        if mgr.license_expires_at:
            linii.append(f"{'Expirată la' if is_ro else 'Expired on'}: {data(mgr.license_expires_at)}")
        return "\n".join([*linii, "", obtine])
    if mgr.status == "expired":
        return "\n".join(["❌ Perioada de test s-a încheiat" if is_ro else "❌ The free trial has ended", "", obtine])
    stare = "❌ Fără licență: senzorii nu se actualizează." if is_ro else "❌ No license: sensors do not update."
    return "\n".join([stare, "", obtine])


class MyEngieOptionsFlow(config_entries.OptionsFlow):
    """OptionsFlow — modificare setări + licență."""

    def __init__(self) -> None:
        self._username: str = ""
        self._password: str = ""
        self._update_interval: int = DEFAULT_UPDATE_INTERVAL
        self._api: MyEngieApiClient | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Afișează meniul principal cu opțiunile disponibile."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "settings",
                "licenta",
            ],
        )

    async def async_step_licenta(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Formular pentru activarea / vizualizarea licenței MyENGIE România."""
        from .license import LicenseManager

        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        is_ro = self.hass.config.language == "ro"

        # Obține LicenseManager
        mgr: LicenseManager | None = self.hass.data.get(DOMAIN, {}).get(
            LICENSE_DATA_KEY
        )
        if mgr is None:
            mgr = LicenseManager(self.hass)
            await mgr.async_load()

        description_placeholders["license_status"] = _status_licenta(mgr, is_ro)

        if user_input is not None:
            cheie = user_input.get(CONF_LICENSE_KEY, "").strip()

            if not cheie:
                errors["base"] = "license_key_empty"
            elif len(cheie) < 10:
                errors["base"] = "license_key_invalid"
            else:
                # Activare prin API
                result = await mgr.async_activate(cheie)

                if result.get("success"):
                    from homeassistant.components import (
                        persistent_notification,
                    )

                    persistent_notification.async_create(
                        self.hass,
                        f"Licența MyENGIE este activă ({_tip_licenta(mgr.license_type, True)}).",
                        title="Licență activată",
                        notification_id="myengie_license_activated",
                    )
                    return self.async_create_entry(
                        data=self.config_entry.options
                    )

                # Mapare erori API
                api_error = result.get("error", "unknown_error")
                # Codurile WebAPI /activate + erorile locale
                error_map = {
                    "invalid_key": "license_key_invalid",
                    "already_used": "license_already_used",
                    "expired_key": "license_key_expired",
                    "fingerprint_mismatch": "license_fingerprint_mismatch",
                    "network_error": "license_network_error",
                    "http_502": "license_network_error",
                    "http_503": "license_network_error",  # server temporar ocupat
                    "http_504": "license_network_error",
                }
                errors["base"] = error_map.get(api_error, "license_server_error")

        schema = vol.Schema(
            {
                vol.Optional(CONF_LICENSE_KEY): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                        suffix="ENGIE-XXXX-XXXX-XXXX-XXXX",
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="licenta",
            data_schema=schema,
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pasul 1: Modificare credențiale."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input["username"]
            password = user_input["password"]
            update_interval = user_input.get(
                "update_interval", DEFAULT_UPDATE_INTERVAL
            )

            session = async_get_clientsession(self.hass)
            self._api = MyEngieApiClient(session, username, password)

            conflict = any(
                e.entry_id != self.config_entry.entry_id
                and e.unique_id == username.lower()
                for e in self.hass.config_entries.async_entries(DOMAIN)
            )
            login_result = (
                "already_configured" if conflict else await self._api.async_login()
            )

            if login_result == MyEngieApiClient.LOGIN_OK:
                _store_token(self.hass, username, self._api)

                # Actualizăm config entry cu noile credențiale
                new_data = dict(self.config_entry.data)
                new_data.update({
                    "username": username,
                    "password": password,
                    "update_interval": update_interval,
                    "token_data": self._api.export_token_data(),
                })
                _update_and_reload(
                    self.hass,
                    self.config_entry,
                    new_data,
                    title=f"MyENGIE România ({username})",
                    unique_id=username.lower(),
                )
                return self.async_create_entry(data=dict(self.config_entry.options))
            else:
                errors["base"] = login_result

        current = self.config_entry.data

        schema = vol.Schema(
            {
                vol.Required(
                    "username", default=current.get("username", "")
                ): str,
                vol.Required(
                    "password", default=current.get("password", "")
                ): str,
                vol.Required(
                    "update_interval",
                    default=current.get("update_interval", DEFAULT_UPDATE_INTERVAL),
                ): vol.All(int, vol.Range(min=3600)),
            }
        )

        return self.async_show_form(
            step_id="settings", data_schema=schema, errors=errors
        )
