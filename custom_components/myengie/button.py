"""Platforma Button pentru MyENGIE România (Engie Romania).

Buton per instalație per POC pentru trimiterea autocitirilor.
Engie API: POST /v1/index cu form-urlencoded body.

Pattern entity_id: button.myengie_{poc}_{div_short}_trimite_index
Device: un serviciu per POC per utilitate.
"""

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTRIBUTION, DOMAIN, LICENSE_DATA_KEY
from .coordinator import MyEngieCoordinator

_LOGGER = logging.getLogger(__name__)


# ═══════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════

def _div_short(division: str) -> str:
    """Returnează eticheta scurtă pt utilitate (entity_id suffix)."""
    if division == "gaz":
        return "gaz"
    if division == "elec":
        return "electricitate"
    return division


def _div_label(division: str) -> str:
    """Returnează eticheta afișabilă pt utilitate."""
    if division == "gaz":
        return "Gaz"
    if division == "elec":
        return "Energie Electrică"
    return division


def _utility_device(poc: str, div_short: str, div_label: str) -> DeviceInfo:
    """Device info per POC per utilitate — un serviciu per utilitate."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"account_{poc}_{div_short}")},
        name=f"MyENGIE România ({poc}) {div_label}",
        manufacturer="Ciprian Nicolae (cnecrea)",
        model="MyENGIE România (Engie Romania)",
        entry_type=DeviceEntryType.SERVICE,
    )


# ═══════════════════════════════════════════════
# SETUP
# ═══════════════════════════════════════════════

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configurează butoanele pentru trimiterea autocitirilor.

    Iterează prin TOATE POC-urile și instalațiile disponibile.
    """
    coordinator: MyEngieCoordinator = config_entry.runtime_data.coordinator

    # Verificare licență — fără licență, fără butoane
    mgr = hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
    if not mgr or not mgr.is_valid:
        _LOGGER.debug("[MyENGIE:Button] Licență invalidă — nu se creează butoane")
        return

    data = coordinator.data or {}
    pocs_data = data.get("pocs_data", {})

    buttons: list[ButtonEntity] = []

    for poc_number, poc_data in pocs_data.items():
        pa = poc_data.get("pa", "")
        divisions = poc_data.get("divisions", {})
        details = divisions.get("details", {})

        # Gaz installations
        for inst_nr in divisions.get("gaz", []):
            # Caută detalii instalație din divisions.details
            inst_detail = _find_installation_detail(details, inst_nr)
            buttons.append(
                TrimiteIndexButton(
                    coordinator, poc_number, pa, "gaz", inst_nr, inst_detail
                )
            )

        # Elec installations
        for inst_nr in divisions.get("elec", []):
            inst_detail = _find_installation_detail(details, inst_nr)
            buttons.append(
                TrimiteIndexButton(
                    coordinator, poc_number, pa, "elec", inst_nr, inst_detail
                )
            )

    if buttons:
        _LOGGER.debug(
            "[MyENGIE:Button] Se adaugă %d butoane pentru %d POC-uri (entry_id=%s).",
            len(buttons), len(pocs_data), config_entry.entry_id,
        )
        async_add_entities(buttons)


def _find_installation_detail(details: dict, inst_nr: str) -> dict:
    """Caută detaliile unei instalații din divisions.details.

    Cheile sunt în format "{inst_nr}_{serial}" — caută cea care începe cu inst_nr.
    """
    for key, detail in details.items():
        if key.startswith(f"{inst_nr}_"):
            return detail if isinstance(detail, dict) else {}
    return {}


# ═══════════════════════════════════════════════
# CLASĂ DE BAZĂ — PATTERN IDENTIC CU VREAULANOVA
# ═══════════════════════════════════════════════

class MyEngieBaseButton(ButtonEntity):
    """Bază pentru toate butoanele MyENGIE România — custom entity_id."""

    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: MyEngieCoordinator,
        poc: str,
        div_short: str = "gaz",
        div_label: str = "Gaz",
    ) -> None:
        self._coordinator = coordinator
        self._poc = poc
        self._div_short = div_short
        self._div_label = div_label
        self._custom_entity_id: str | None = None

    @property
    def _license_valid(self) -> bool:
        """Verifică dacă licența este validă (real-time)."""
        mgr = self._coordinator.hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
        return mgr.is_valid if mgr else False

    @property
    def entity_id(self) -> str | None:
        return self._custom_entity_id

    @entity_id.setter
    def entity_id(self, value: str) -> None:
        self._custom_entity_id = value

    @property
    def device_info(self) -> DeviceInfo:
        return _utility_device(self._poc, self._div_short, self._div_label)


# ═══════════════════════════════════════════════
# BUTOANE
# ═══════════════════════════════════════════════

class TrimiteIndexButton(MyEngieBaseButton):
    """Buton pentru trimiterea autocitirilor la MyENGIE România API.

    Engie API: POST /v1/index cu form-urlencoded body.
    Un buton per instalație per POC.
    """

    _attr_attribution = ATTRIBUTION

    def __init__(
        self,
        coordinator: MyEngieCoordinator,
        poc: str,
        pa: str,
        division: str,
        inst_nr: str,
        inst_detail: dict,
    ):
        """Inițializare buton trimitere index."""
        ds = _div_short(division)
        dl = _div_label(division)
        super().__init__(coordinator, poc, ds, dl)
        self._pa = pa
        self._division = division
        self._inst_nr = inst_nr
        self._inst_detail = inst_detail

        self._pod = inst_detail.get("pod", "")
        self._serial = inst_detail.get("serial_number", inst_detail.get("serie_contor", inst_detail.get("serial", "")))

        self._attr_name = "Trimite index"
        self._attr_unique_id = f"{DOMAIN}_{poc}_{ds}_trimite_index_{inst_nr}"
        self._attr_icon = "mdi:fire" if division == "gaz" else "mdi:flash"

        # Custom entity_id: button.myengie_{poc}_{div_short}_trimite_index
        self._custom_entity_id = (
            f"button.{DOMAIN}_{poc}_{ds}_trimite_index"
        )

    @property
    def available(self) -> bool:
        """Butonul e disponibil doar dacă licența e validă și coordinator-ul e ok."""
        return self._license_valid and self._coordinator.last_update_success

    async def async_press(self) -> None:
        """Trimite autocitirea la MyENGIE România API.

        Engie folosește POST /v1/index cu form-urlencoded body.
        Parametrii: poc, division, pa, installation_number, reading_value, serie_contor.
        """
        if not self._license_valid:
            _LOGGER.warning(
                "[MyENGIE:Button] Licență invalidă — trimiterea indexului nu e posibilă."
            )
            return

        # Citește valoarea din input_number entity
        input_entity_id = (
            f"input_number.{DOMAIN}_{self._poc}_{self._div_short}_{self._inst_nr}_index"
        )
        state = self._coordinator.hass.states.get(input_entity_id)

        if not state or state.state in ("unknown", "unavailable"):
            _LOGGER.error(
                "[MyENGIE:Button] Entitatea %s nu există sau nu are valoare.",
                input_entity_id,
            )
            return

        try:
            index_value = int(float(state.state))
        except (ValueError, TypeError):
            _LOGGER.error(
                "[MyENGIE:Button] Valoare invalidă în %s: %s",
                input_entity_id, state.state,
            )
            return

        # Construiește payload-ul Engie (form-urlencoded)
        # Câmpuri confirmate din APK IndexApi.java sendIndex$lambda$8
        # și validate cu debug_myengie.py --send-index (status 200 OK)
        payload = {
            "poc_number": self._poc,
            "pa": self._pa,
            "installation_number": self._inst_nr,
            "division": self._division,
            "index": str(index_value),
        }
        if self._serial:
            payload["serie_contor"] = self._serial

        _LOGGER.info(
            "[MyENGIE:Button] Trimitere autocitire: poc=%s, division=%s, inst=%s, "
            "newIndex=%s, pa=%s",
            self._poc, self._division, self._inst_nr, index_value, self._pa,
        )

        result = await self._coordinator.api_client.async_submit_self_reading(payload)

        if result:
            _LOGGER.info(
                "[MyENGIE:Button] Autocitire trimisă cu succes pentru inst %s.",
                self._inst_nr,
            )
            await self._coordinator.async_request_refresh()
        else:
            _LOGGER.error(
                "[MyENGIE:Button] Trimiterea autocitirilor a eșuat pentru inst %s.",
                self._inst_nr,
            )
