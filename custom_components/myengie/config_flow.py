"""
ConfigFlow și OptionsFlow pentru integrarea MyENGIE România (Engie Romania).

Utilizatorul introduce email + parolă.
Engie nu suportă MFA — pașii MFA sunt stuburi care nu vor fi niciodată atinși.
Licența se gestionează din OptionsFlow (pasul "licenta").
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
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

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> MyEngieOptionsFlow:
        return MyEngieOptionsFlow()


# ------------------------------------------------------------------
# OptionsFlow
# ------------------------------------------------------------------

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

        # Informații pentru descrierea formularului
        server_status = mgr.status

        if server_status == "licensed":
            from datetime import datetime

            tip = mgr.license_type or "necunoscut"
            status_lines = [f"✅ Licență activă ({tip})"]

            if mgr.license_key_masked:
                status_lines[0] += f" — {mgr.license_key_masked}"

            if mgr.activated_at:
                act_date = datetime.fromtimestamp(
                    mgr.activated_at
                ).strftime("%d.%m.%Y %H:%M")
                status_lines.append(f"Activată la: {act_date}")

            if mgr.license_expires_at:
                exp_date = datetime.fromtimestamp(
                    mgr.license_expires_at
                ).strftime("%d.%m.%Y %H:%M")
                status_lines.append(f"📅 Expiră la: {exp_date}")
            elif tip == "perpetual":
                status_lines.append("Valabilitate: nelimitată (perpetuă)")

            description_placeholders["license_status"] = "\n".join(
                status_lines
            )

        elif server_status == "trial":
            days = mgr.trial_days_remaining
            if is_ro:
                status_lines = [
                    f"⏳ Evaluare — {days} zile rămase",
                    "",
                    f"🛒 Obține licență: {LICENSE_PURCHASE_URL}",
                ]
            else:
                status_lines = [
                    f"⏳ Trial — {days} days remaining",
                    "",
                    f"🛒 Get a license: {LICENSE_PURCHASE_URL}",
                ]
            description_placeholders["license_status"] = "\n".join(status_lines)
        elif server_status == "expired":
            from datetime import datetime

            status_lines = ["❌ Licență expirată"]

            if mgr.activated_at:
                act_date = datetime.fromtimestamp(
                    mgr.activated_at
                ).strftime("%d.%m.%Y")
                status_lines.append(f"Activată la: {act_date}")
            if mgr.license_expires_at:
                exp_date = datetime.fromtimestamp(
                    mgr.license_expires_at
                ).strftime("%d.%m.%Y")
                status_lines.append(f"Expirată la: {exp_date}")

            status_lines.append("")
            if is_ro:
                status_lines.append(
                    f"🛒 Obține licență: {LICENSE_PURCHASE_URL}"
                )
            else:
                status_lines.append(
                    f"🛒 Get a license: {LICENSE_PURCHASE_URL}"
                )

            description_placeholders["license_status"] = "\n".join(
                status_lines
            )
        else:
            if is_ro:
                status_lines = [
                    "❌ Fără licență — funcționalitate blocată",
                    "",
                    f"🛒 Obține licență: {LICENSE_PURCHASE_URL}",
                ]
            else:
                status_lines = [
                    "❌ No license — functionality blocked",
                    "",
                    f"🛒 Get a license: {LICENSE_PURCHASE_URL}",
                ]
            description_placeholders["license_status"] = "\n".join(status_lines)

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

                    _LICENSE_TYPE_RO = {
                        "monthly": "lunară",
                        "yearly": "anuală",
                        "perpetual": "perpetuă",
                        "trial": "evaluare",
                    }
                    tip_ro = _LICENSE_TYPE_RO.get(
                        mgr.license_type, mgr.license_type or "necunoscut"
                    )

                    persistent_notification.async_create(
                        self.hass,
                        f"Licența MyENGIE România a fost activată cu succes! "
                        f"Tip: {tip_ro}.",
                        title="Licență activată",
                        notification_id="myengie_license_activated",
                    )
                    return self.async_create_entry(
                        data=self.config_entry.options
                    )

                # Mapare erori API
                api_error = result.get("error", "unknown_error")
                error_map = {
                    "invalid_key": "license_key_invalid",
                    "already_used": "license_already_used",
                    "expired_key": "license_key_expired",
                    "fingerprint_mismatch": "license_fingerprint_mismatch",
                    "invalid_signature": "license_server_error",
                    "network_error": "license_network_error",
                    "server_error": "license_server_error",
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

            login_result = await self._api.async_login()

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
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=new_data
                )

                await self.hass.config_entries.async_reload(
                    self.config_entry.entry_id
                )

                return self.async_create_entry(data={})
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
