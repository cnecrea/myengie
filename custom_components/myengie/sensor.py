"""Platforma Sensor pentru MyENGIE România (Engie Romania).

Pattern entity_id:
  - Per utilitate:   sensor.{DOMAIN}_{poc}_{div}_{suffix}
  - Per instalație:  sensor.{DOMAIN}_{poc}_{div}_{suffix}_{installation}

TOȚI senzorii sunt per utilitate — apar sub fiecare device separat.
Pattern 1:1 cu vreaulanova: _attr_has_entity_name = False, custom entity_id property.

Device-uri: un serviciu per POC per utilitate (gaz / electricitate).
  - MyENGIE România (5001464750) Gaz
  - MyENGIE România (5001464750) Energie Electrică

Conform STANDARD-LICENTA.md:
- Licență invalidă → doar LicentaNecesaraSensor
- Licență validă → cleanup LicentaNecesaraSensor + senzori normali
- Fiecare senzor are _license_valid property real-time
"""

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, LICENSE_DATA_KEY, MONTHS_RO
from .coordinator import MyEngieCoordinator

_LOGGER = logging.getLogger(__name__)


# ═══════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════

def _is_license_valid(hass: HomeAssistant) -> bool:
    """Verifică dacă licența este validă (real-time)."""
    mgr = hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
    if mgr is None:
        return False
    return mgr.is_valid


def _division_short(division: str) -> str:
    """Returnează eticheta scurtă pt utilitate (entity_id suffix)."""
    if division == "gaz":
        return "gaz"
    if division in ("elec", "electricity"):
        return "electricitate"
    return division


def _division_label(division: str) -> str:
    """Returnează eticheta afișabilă pt utilitate."""
    if division == "gaz":
        return "Gaz"
    if division in ("elec", "electricity"):
        return "Energie Electrică"
    return division


def _division_api_type(div_short: str) -> str:
    """Convertește div_short înapoi la tipul API."""
    if div_short == "gaz":
        return "gaz"
    if div_short == "electricitate":
        return "elec"
    return div_short


def _utility_device(poc: str, div_short: str, div_label: str) -> DeviceInfo:
    """Device info per POC per utilitate — un serviciu per utilitate."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"account_{poc}_{div_short}")},
        name=f"MyENGIE România ({poc}) {div_label}",
        manufacturer="Ciprian Nicolae (cnecrea)",
        model="MyENGIE România (Engie Romania)",
        entry_type=DeviceEntryType.SERVICE,
    )


def _unit_for_division(division: str) -> str | None:
    """Returnează unitatea HA potrivită pe baza tipului de utilitate."""
    if division in ("elec", "electricity", "electricitate"):
        return UnitOfEnergy.KILO_WATT_HOUR
    if division == "gaz":
        return UnitOfVolume.CUBIC_METERS
    return None


# Luni românești (lowercase) — pentru formatarea datelor
_MONTHS_RO_LOWER = [
    "ianuarie", "februarie", "martie", "aprilie", "mai", "iunie",
    "iulie", "august", "septembrie", "octombrie", "noiembrie", "decembrie",
]


def _format_date_ro(date_str: str) -> str:
    """Convertește data în format românesc: '4 martie 2026'."""
    if not date_str:
        return "N/A"
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f",
                "%d-%m-%Y"):
        try:
            clean = date_str[:19] if "T" in date_str else date_str
            dt = datetime.strptime(clean, fmt)
            month_name = _MONTHS_RO_LOWER[dt.month - 1]
            return f"{dt.day} {month_name} {dt.year}"
        except ValueError:
            continue
    return date_str


def _format_amount(val) -> str:
    """Formatează suma: 2.675,47 lei."""
    try:
        num = float(val)
    except (ValueError, TypeError):
        return "0 lei"
    formatted = f"{num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{formatted} lei"


# ═══════════════════════════════════════════════
# CLASĂ DE BAZĂ — PATTERN IDENTIC CU VREAULANOVA
# ═══════════════════════════════════════════════

class MyEngieBaseSensor(CoordinatorEntity[MyEngieCoordinator], SensorEntity):
    """Bază pentru toți senzorii MyENGIE România — include verificare licență + custom entity_id."""

    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: MyEngieCoordinator,
        poc: str,
        div_short: str = "gaz",
        div_label: str = "Gaz",
    ) -> None:
        super().__init__(coordinator)
        self._poc = poc
        self._div_short = div_short
        self._div_label = div_label
        self._custom_entity_id: str | None = None

    def _poc_data(self) -> dict:
        """Returnează datele specifice POC-ului acestui senzor."""
        data = self.coordinator.data or {}
        return data.get("pocs_data", {}).get(self._poc, {})

    def _iter_installations(self, div_api: str | None = None) -> list[dict]:
        """Iterează prin toate instalațiile din index_readings pentru division.

        Gestionează structura API: index_readings[div] = [[{poc, installations: [...]}], ...]
        Returnează lista flatten de dicts de instalație.
        """
        if div_api is None:
            div_api = _division_api_type(self._div_short)
        poc_d = self._poc_data()
        readings_list = poc_d.get("index_readings", {}).get(div_api, [])
        result: list[dict] = []

        for item in readings_list:
            if isinstance(item, dict):
                # Direct dict cu "installations"
                for inst in item.get("installations", []):
                    if isinstance(inst, dict):
                        result.append(inst)
            elif isinstance(item, list):
                # Lista de dicts (API returnează data ca listă)
                for sub_item in item:
                    if isinstance(sub_item, dict):
                        for inst in sub_item.get("installations", []):
                            if isinstance(inst, dict):
                                result.append(inst)
        return result

    @property
    def _license_valid(self) -> bool:
        """Verifică dacă licența este validă (real-time)."""
        mgr = self.coordinator.hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
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
# LICENȚĂ NECESARĂ — SENZOR DEDICAT
# ═══════════════════════════════════════════════

class LicentaNecesaraSensor(MyEngieBaseSensor):
    """Senzor care afișează 'Licență necesară' când nu există licență validă."""

    _attr_icon = "mdi:license"
    _attr_translation_key = "licenta_necesara"

    def __init__(
        self,
        coordinator: MyEngieCoordinator,
        poc: str,
        div_short: str = "gaz",
        div_label: str = "Gaz",
    ) -> None:
        super().__init__(coordinator, poc, div_short, div_label)
        self._attr_name = "MyENGIE România"
        self._attr_unique_id = f"{DOMAIN}_licenta_{poc}"
        self._custom_entity_id = f"sensor.{DOMAIN}_{poc}_licenta"

    @property
    def native_value(self):
        return "Licență necesară"

    @property
    def extra_state_attributes(self):
        return {
            "status": "Licență necesară",
            "info": "Integrarea necesită o licență validă pentru a funcționa.",
            "attribution": ATTRIBUTION,
        }


# ═══════════════════════════════════════════════
# BAZĂ PER INSTALAȚIE
# ═══════════════════════════════════════════════

class MyEngieInstallationBaseSensor(MyEngieBaseSensor):
    """Bază pentru senzori per instalație (contor)."""

    def __init__(self, coordinator, poc, div_short, div_label, installation_number: str, pod: str = ""):
        super().__init__(coordinator, poc, div_short, div_label)
        self._installation_number = installation_number
        self._pod = pod


# ═══════════════════════════════════════════════
# ASYNC_SETUP_ENTRY
# ═══════════════════════════════════════════════

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configurează senzorii din config entry.

    Iterează prin TOATE POC-urile din pocs_data.
    TOȚI senzorii sunt per utilitate — apar sub fiecare device (gaz / electricitate).
    """
    coordinator: MyEngieCoordinator = entry.runtime_data.coordinator
    data = coordinator.data or {}
    pocs_data = data.get("pocs_data", {})

    license_valid = _is_license_valid(hass)

    # Fallback POC — pentru licență invalidă (când nu avem pocs_data)
    fallback_poc = ""
    if pocs_data:
        fallback_poc = next(iter(pocs_data.keys()), "")
    if not fallback_poc:
        fallback_poc = entry.entry_id[:8]

    if not license_valid:
        # ── Licență INVALIDĂ: curăță senzorii normali + creează LicentaNecesaraSensor ──
        licenta_uid = f"{DOMAIN}_licenta_{fallback_poc}"
        registru = er.async_get(hass)
        for entry_reg in er.async_entries_for_config_entry(registru, entry.entry_id):
            if (
                entry_reg.domain == "sensor"
                and entry_reg.unique_id != licenta_uid
            ):
                registru.async_remove(entry_reg.entity_id)
                _LOGGER.debug(
                    "[MyENGIE] Senzor orfan eliminat (licență expirată): %s",
                    entry_reg.entity_id,
                )
        async_add_entities(
            [LicentaNecesaraSensor(coordinator, fallback_poc)],
            update_before_add=True,
        )
        return

    # ── Licență VALIDĂ: curăță LicentaNecesaraSensor orfan (per fiecare POC) ──
    registru = er.async_get(hass)
    for poc in list(pocs_data.keys()) + [fallback_poc]:
        licenta_uid = f"{DOMAIN}_licenta_{poc}"
        entitate_licenta = registru.async_get_entity_id("sensor", DOMAIN, licenta_uid)
        if entitate_licenta is not None:
            registru.async_remove(entitate_licenta)
            _LOGGER.debug(
                "[MyENGIE] LicentaNecesaraSensor orfan eliminat: %s",
                entitate_licenta,
            )

    entities: list[SensorEntity] = []

    # ── Iterăm prin TOATE POC-urile din pocs_data ──
    for poc, poc_data in pocs_data.items():
        divisions = poc_data.get("divisions", {})
        divisions_details = divisions.get("details", {})

        # Colectăm utilitățile disponibile din divisions
        seen_divisions: set[str] = set()

        # Gaz installations
        gaz_insts = divisions.get("gaz", [])
        if gaz_insts:
            div_short = "gaz"
            div_label = "Gaz"
            seen_divisions.add(div_short)

            # ── Senzori la nivel de utilitate (o dată per gaz) ──
            entities.append(MyEngieBalanceSensor(coordinator, poc, div_short, div_label))
            entities.append(MyEngieCitirePermisaSensor(coordinator, poc, div_short, div_label))
            entities.append(MyEngieArhivaFacturiSensor(coordinator, poc, div_short, div_label))
            entities.append(MyEngieArhivaPlatiSensor(coordinator, poc, div_short, div_label))
            entities.append(MyEngieFacturaRestantaSensor(coordinator, poc, div_short, div_label))
            entities.append(MyEngieConsumGraficSensor(coordinator, poc, div_short, div_label))
            entities.append(MyEngieContractSensor(coordinator, poc, div_short, div_label))
            entities.append(MyEngieDateUtilizatorSensor(
                coordinator, poc, div_short, div_label, pa=poc_data.get("pa", ""),
            ))

            # Revizie tehnică — doar gaz
            entities.append(MyEngieRevizieTehnicaSensor(coordinator, poc, div_short, div_label))

            # ── Senzori per instalație (contor) ──
            for inst_nr in gaz_insts:
                inst_str = str(inst_nr)
                # Găsește POD-ul din details
                pod = ""
                serie = ""
                for _key, detail in divisions_details.items():
                    if isinstance(detail, dict) and str(detail.get("installation_number", "")) == inst_str:
                        pod = detail.get("pod", "")
                        serie = str(detail.get("serie_contor", detail.get("meterSerial", "")))
                        break
                entities.append(MyEngieIndexContorSensor(
                    coordinator, poc, div_short, div_label, inst_str, pod
                ))
                entities.append(MyEngieIstoricIndexSensor(
                    coordinator, poc, div_short, div_label, inst_str, pod, serie
                ))

        # Elec installations
        elec_insts = divisions.get("elec", [])
        if elec_insts:
            div_short = "electricitate"
            div_label = "Energie Electrică"
            seen_divisions.add(div_short)

            entities.append(MyEngieBalanceSensor(coordinator, poc, div_short, div_label))
            entities.append(MyEngieCitirePermisaSensor(coordinator, poc, div_short, div_label))
            entities.append(MyEngieArhivaFacturiSensor(coordinator, poc, div_short, div_label))
            entities.append(MyEngieArhivaPlatiSensor(coordinator, poc, div_short, div_label))
            entities.append(MyEngieFacturaRestantaSensor(coordinator, poc, div_short, div_label))
            entities.append(MyEngieConsumGraficSensor(coordinator, poc, div_short, div_label))
            entities.append(MyEngieContractSensor(coordinator, poc, div_short, div_label))
            entities.append(MyEngieDateUtilizatorSensor(
                coordinator, poc, div_short, div_label, pa=poc_data.get("pa", ""),
            ))

            for inst_nr in elec_insts:
                inst_str = str(inst_nr)
                pod = ""
                serie = ""
                for _key, detail in divisions_details.items():
                    if isinstance(detail, dict) and str(detail.get("installation_number", "")) == inst_str:
                        pod = detail.get("pod", "")
                        serie = str(detail.get("serie_contor", detail.get("meterSerial", "")))
                        break
                entities.append(MyEngieIndexContorSensor(
                    coordinator, poc, div_short, div_label, inst_str, pod
                ))
                entities.append(MyEngieIstoricIndexSensor(
                    coordinator, poc, div_short, div_label, inst_str, pod, serie
                ))

        # Dacă niciun POC nu are divisions (date insuficiente), creăm senzori gaz implicit
        if not seen_divisions:
            div_short = "gaz"
            div_label = "Gaz"
            entities.append(MyEngieBalanceSensor(coordinator, poc, div_short, div_label))
            entities.append(MyEngieArhivaFacturiSensor(coordinator, poc, div_short, div_label))
            entities.append(MyEngieFacturaRestantaSensor(coordinator, poc, div_short, div_label))

    _LOGGER.debug(
        "[MyENGIE] Se creează %d senzori pentru %d POC-uri",
        len(entities), len(pocs_data),
    )
    async_add_entities(entities)


# ═══════════════════════════════════════════════
# SENZORI CONT (PER UTILITATE)
# ═══════════════════════════════════════════════

class MyEngieBalanceSensor(MyEngieBaseSensor):
    """Sold total (Lei) — per utilitate.

    Entity ID: sensor.{DOMAIN}_{poc}_{div}_sold_total
    """

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "RON"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:cash"

    def __init__(self, coordinator, poc, div_short, div_label):
        super().__init__(coordinator, poc, div_short, div_label)
        self._attr_unique_id = f"{DOMAIN}_{poc}_{div_short}_balance"
        self._attr_name = "Sold total"
        self._custom_entity_id = f"sensor.{DOMAIN}_{poc}_{div_short}_sold_total"

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return "Licență necesară"
        poc_d = self._poc_data()
        balance = poc_d.get("balance", {})
        total = balance.get("total", 0)
        try:
            return float(total)
        except (ValueError, TypeError):
            return 0


class MyEngieCitirePermisaSensor(MyEngieBaseSensor):
    """Citire permisă — Da/Nu pe baza verificării dacă suntem în perioada de autocitire.

    Logica reală:
      - permite_index == True din API NU e suficient
      - Trebuie verificat dacă data curentă e în intervalul [startDate, endDate]
      - "Da" DOAR dacă azi e în intervalul de autocitire
      - "Nu" altfel (inclusiv dacă permite_index e True dar nu suntem în perioadă)

    Atribute separate: Început perioadă, Sfârșit perioadă (formatate românesc).

    Entity ID: sensor.{DOMAIN}_{poc}_{div}_citire_permisa
    """

    _attr_icon = "mdi:clock-alert-outline"

    def __init__(self, coordinator, poc, div_short, div_label):
        super().__init__(coordinator, poc, div_short, div_label)
        self._attr_unique_id = f"{DOMAIN}_{poc}_{div_short}_citire_permisa"
        self._attr_name = "Citire permisă"
        self._custom_entity_id = f"sensor.{DOMAIN}_{poc}_{div_short}_citire_permisa"

    def _get_read_period(self) -> tuple[str, str]:
        """Extrage startDate și endDate din prima instalație cu date disponibile."""
        for inst in self._iter_installations():
            next_dates = inst.get("next_read_dates") or {}
            start = next_dates.get("startDate", "")
            end = next_dates.get("endDate", "")
            if start or end:
                return (start, end)
        return ("", "")

    @staticmethod
    def _parse_date(date_str: str):
        """Parsează dată din format dd-mm-yyyy sau dd.mm.yyyy."""
        if not date_str:
            return None
        for fmt in ("%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except ValueError:
                continue
        return None

    def _is_in_period(self) -> bool:
        """Verifică dacă data curentă e în intervalul de autocitire."""
        start_str, end_str = self._get_read_period()
        start_date = self._parse_date(start_str)
        end_date = self._parse_date(end_str)
        if not start_date or not end_date:
            return False
        today = datetime.now().date()
        return start_date <= today <= end_date

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return "Licență necesară"
        # Verificăm dacă suntem ÎN perioadă, nu doar dacă API-ul zice permite_index
        return "Da" if self._is_in_period() else "Nu"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        start_str, end_str = self._get_read_period()
        attrs: dict[str, Any] = {}
        if start_str:
            attrs["Început perioadă"] = _format_date_ro(start_str)
        if end_str:
            attrs["Sfârșit perioadă"] = _format_date_ro(end_str)
        attrs["attribution"] = ATTRIBUTION
        return attrs


# ═══════════════════════════════════════════════
# ARHIVE (ANUL CURENT) — PER UTILITATE
# ═══════════════════════════════════════════════

class MyEngieArhivaFacturiSensor(MyEngieBaseSensor):
    """Arhivă facturi — nr facturi pe anul curent PER UTILITATE.

    Entity ID: sensor.{DOMAIN}_{poc}_{div}_arhiva_facturi
    """

    _attr_icon = "mdi:file-document-multiple-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, poc, div_short, div_label):
        super().__init__(coordinator, poc, div_short, div_label)
        self._div_api = _division_api_type(div_short)
        self._attr_unique_id = f"{DOMAIN}_{poc}_{div_short}_arhiva_facturi"
        self._attr_name = "Arhivă facturi"
        self._custom_entity_id = f"sensor.{DOMAIN}_{poc}_{div_short}_arhiva_facturi"

    def _invoices_current_year(self) -> list[dict]:
        """Filtrează facturile pe anul curent și utilitatea senzorului."""
        poc_d = self._poc_data()
        invoices_raw = poc_d.get("invoices", [])
        current_year = str(datetime.now().year)
        result = []

        # invoices_raw poate fi o listă de wrapper-uri cu "invoices" array
        invoices = []
        if isinstance(invoices_raw, list):
            for item in invoices_raw:
                if isinstance(item, dict) and "invoices" in item:
                    invoices.extend(item.get("invoices", []))
                elif isinstance(item, dict):
                    invoices.append(item)
        elif isinstance(invoices_raw, dict):
            invoices = invoices_raw.get("invoices", [])

        for inv in invoices:
            if not isinstance(inv, dict):
                continue
            invoiced_at = inv.get("invoiced_at", "")
            division = inv.get("division", "")
            if invoiced_at and current_year in invoiced_at and division == self._div_api:
                result.append(inv)
        return result

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return "Licență necesară"
        return len(self._invoices_current_year())

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        invoices = self._invoices_current_year()
        attrs: dict[str, Any] = {}

        total = 0.0
        for inv in invoices:
            date_ro = _format_date_ro(inv.get("invoiced_at", ""))
            try:
                amount = float(inv.get("total", 0))
            except (ValueError, TypeError):
                amount = 0.0
            total += amount
            attrs[f"Emisă pe {date_ro}"] = _format_amount(amount)

        attrs["Total facturi"] = str(len(invoices))
        attrs["Total facturat"] = _format_amount(total)
        return attrs


class MyEngieArhivaPlatiSensor(MyEngieBaseSensor):
    """Arhivă plăți — nr plăți pe anul curent — per utilitate.

    Entity ID: sensor.{DOMAIN}_{poc}_{div}_arhiva_plati
    """

    _attr_icon = "mdi:cash-check"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, poc, div_short, div_label):
        super().__init__(coordinator, poc, div_short, div_label)
        self._attr_unique_id = f"{DOMAIN}_{poc}_{div_short}_arhiva_plati"
        self._attr_name = "Arhivă plăți"
        self._custom_entity_id = f"sensor.{DOMAIN}_{poc}_{div_short}_arhiva_plati"

    def _extract_payments_list(self) -> list[dict]:
        """Extrage lista de plăți din coordinator.

        API response (din PaymentsApi.java APK):
          GET v1/invoices/payment/history/{pa}?startDate=...&endDate=...
          json.data = [{amount, paid_at, payment_method, payment_location}, ...]

        async_get_payment_history() face raw.get("data", raw) → lista directă
        """
        poc_d = self._poc_data()
        raw = poc_d.get("payments")

        if raw is None:
            return []
        if isinstance(raw, list):
            return [p for p in raw if isinstance(p, dict)]
        if isinstance(raw, dict):
            # Fallback dacă API returnează dict wrapper
            inner = raw.get("data") or raw.get("payments")
            if isinstance(inner, list):
                return [p for p in inner if isinstance(p, dict)]
            return []
        return []

    def _payments_current_year(self) -> list[dict]:
        """Filtrează plățile pe anul curent."""
        all_payments = self._extract_payments_list()
        current_year = str(datetime.now().year)
        result = []
        for pay in all_payments:
            # Câmpul real din APK: "paid_at" (format yyyy-MM-dd, ex: "2026-03-15")
            pay_date = pay.get("paid_at", "")
            if pay_date and current_year in str(pay_date):
                result.append(pay)
        return result

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return "Licență necesară"
        return len(self._payments_current_year())

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        payments = self._payments_current_year()
        attrs: dict[str, Any] = {}

        total = 0.0
        for pay in payments:
            # Câmpuri exacte din APK (PaymentHistoryItem):
            #   amount (double), paid_at (date), payment_method (string), payment_location (string)
            date_ro = _format_date_ro(pay.get("paid_at", ""))
            try:
                amount = float(pay.get("amount", 0))
            except (ValueError, TypeError):
                amount = 0.0
            total += amount
            method = pay.get("payment_method", "")
            location = pay.get("payment_location", "")
            label = f"Plată pe {date_ro}"
            value = _format_amount(amount)
            if method:
                value = f"{value} ({method})"
            attrs[label] = value

        attrs["Total plăți"] = str(len(payments))
        attrs["Total plătit"] = _format_amount(total)
        attrs["attribution"] = ATTRIBUTION
        return attrs


# ═══════════════════════════════════════════════
# SENZORI PER INSTALAȚIE (CONTOR)
# ═══════════════════════════════════════════════

class MyEngieIndexContorSensor(MyEngieInstallationBaseSensor):
    """Index curent contor + date ultima autocitire ca atribute.

    Entity ID: sensor.{DOMAIN}_{poc}_{div}_index_contor_{installation}
    """

    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator, poc, div_short, div_label, installation_number, pod=""):
        super().__init__(coordinator, poc, div_short, div_label, installation_number, pod)
        self._attr_unique_id = f"{DOMAIN}_{poc}_{div_short}_index_contor_{installation_number}"
        self._attr_name = "Index contor"
        self._custom_entity_id = f"sensor.{DOMAIN}_{poc}_{div_short}_index_contor_{installation_number}"
        self._attr_native_unit_of_measurement = _unit_for_division(div_short)

    def _find_installation(self) -> dict | None:
        """Găsește instalația în index_readings."""
        for inst in self._iter_installations():
            if str(inst.get("installation_number", "")) == self._installation_number:
                return inst
        return None

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return "Licență necesară"
        inst = self._find_installation()
        if inst:
            last_index = inst.get("last_index")
            if last_index is not None:
                try:
                    return int(last_index)
                except (ValueError, TypeError):
                    return last_index
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        inst = self._find_installation()
        if not inst:
            return None

        next_dates = inst.get("next_read_dates", {})
        attrs: dict[str, Any] = {
            "POD": inst.get("pod", self._pod),
            "Nr. instalație": self._installation_number,
            "Autocitire": inst.get("autocit", ""),
            "Permite index": "Da" if inst.get("permite_index") else "Nu",
        }
        if next_dates:
            attrs["Perioadă autocitire"] = f"{next_dates.get('startDate', '')} - {next_dates.get('endDate', '')}"

        return attrs


# ═══════════════════════════════════════════════
# SENZORI PER UTILITATE — FACTURI RESTANTE
# ═══════════════════════════════════════════════

class MyEngieFacturaRestantaSensor(MyEngieBaseSensor):
    """Factură restantă — Da/Nu dacă există facturi neachitate.

    Entity ID: sensor.{DOMAIN}_{poc}_{div}_factura_restanta
    """

    _attr_icon = "mdi:file-document-alert"

    def __init__(self, coordinator, poc, div_short, div_label):
        super().__init__(coordinator, poc, div_short, div_label)
        self._div_api = _division_api_type(div_short)
        self._attr_unique_id = f"{DOMAIN}_{poc}_{div_short}_factura_restanta"
        self._attr_name = "Factură restantă"
        self._custom_entity_id = f"sensor.{DOMAIN}_{poc}_{div_short}_factura_restanta"

    def _get_unpaid(self) -> list[dict]:
        """Returnează lista facturilor neachitate."""
        poc_d = self._poc_data()
        invoices_raw = poc_d.get("invoices", [])

        invoices = []
        if isinstance(invoices_raw, list):
            for item in invoices_raw:
                if isinstance(item, dict) and "invoices" in item:
                    invoices.extend(item.get("invoices", []))
                elif isinstance(item, dict):
                    invoices.append(item)

        return [
            inv for inv in invoices
            if isinstance(inv, dict)
            and inv.get("division") == self._div_api
            and inv.get("unpaid", 0) != 0
        ]

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return "Licență necesară"
        unpaid = self._get_unpaid()
        return "Da" if unpaid else "Nu"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        unpaid = self._get_unpaid()
        total = 0.0
        for inv in unpaid:
            try:
                total += float(inv.get("unpaid", inv.get("total", 0)))
            except (ValueError, TypeError):
                pass

        poc_d = self._poc_data()
        balance = poc_d.get("balance", {})

        return {
            "Total restantă": f"{round(total, 2)} RON",
            "Sold total": f"{balance.get('total', '0.00')} RON",
            "Facturi neachitate": len(unpaid),
        }


# ═══════════════════════════════════════════════
# SENZORI PER UTILITATE — REVIZIE TEHNICĂ (GAZ)
# ═══════════════════════════════════════════════

class MyEngieRevizieTehnicaSensor(MyEngieBaseSensor):
    """Revizie tehnică — un singur senzor consolidat per utilitate gaz.

    Entity ID: sensor.{DOMAIN}_{poc}_gaz_revizie_tehnica
    """

    _attr_icon = "mdi:wrench-clock"

    def __init__(self, coordinator, poc, div_short, div_label):
        super().__init__(coordinator, poc, div_short, div_label)
        self._attr_unique_id = f"{DOMAIN}_{poc}_gaz_revizie_tehnica"
        self._attr_name = "Revizie tehnică"
        self._custom_entity_id = f"sensor.{DOMAIN}_{poc}_gaz_revizie_tehnica"

    def _get_inspection(self) -> dict | None:
        """Extrage datele de inspecție din coordinator."""
        poc_d = self._poc_data()
        inspection_data = poc_d.get("inspection", {})
        # Returnează prima inspecție disponibilă
        for _pod, insp in inspection_data.items():
            if isinstance(insp, dict):
                return insp
        return None

    @staticmethod
    def _is_expired(date_str: str) -> bool:
        """Verifică dacă data a trecut."""
        if not date_str:
            return False
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
            try:
                return datetime.strptime(date_str, fmt).date() < datetime.now().date()
            except ValueError:
                continue
        return False

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return "Licență necesară"
        insp = self._get_inspection()
        if insp:
            next_date = insp.get("next_inspection_date", "")
            is_overdue = insp.get("next_inspection_is_overdue", False)
            if is_overdue:
                return "Expirată"
            if next_date:
                if self._is_expired(next_date):
                    return "Expirată"
                return "Validă"
        return "Nedefinit"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        insp = self._get_inspection()
        if not insp:
            return None

        next_type = insp.get("next_inspection_type", "")
        next_type_label = "Verificare" if next_type == "V" else "Revizie" if next_type == "R" else next_type

        return {
            "Data ultimei revizii": _format_date_ro(insp.get("last_revision_date", "")),
            "Data ultimei verificări": _format_date_ro(insp.get("last_verify_date", "")),
            "Data următoarei inspecții": _format_date_ro(insp.get("next_inspection_date", "")),
            "Tipul următoarei inspecții": next_type_label,
            "Depășită": "Da" if insp.get("next_inspection_is_overdue") else "Nu",
        }


# ═══════════════════════════════════════════════
# SENZORI EXTRA — CONSUM GRAFIC
# ═══════════════════════════════════════════════

class MyEngieConsumGraficSensor(MyEngieBaseSensor):
    """Arhiva consum lunar — suma consumului pe anul curent + detalii per lună.

    Entity ID: sensor.{DOMAIN}_{poc}_{div}_consum_grafic
    Atribut principal: total consum anul curent (suma lunilor).
    Atribute secundare: consum per lună (doar anul curent).
    """

    _attr_icon = "mdi:chart-line"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, poc, div_short, div_label):
        super().__init__(coordinator, poc, div_short, div_label)
        self._attr_unique_id = f"{DOMAIN}_{poc}_{div_short}_consum_grafic"
        self._attr_name = "Arhivă consum lunar"
        self._custom_entity_id = f"sensor.{DOMAIN}_{poc}_{div_short}_consum_grafic"
        self._attr_native_unit_of_measurement = _unit_for_division(div_short)

    def _current_year_entries(self) -> list[dict]:
        """Returnează doar intrările din consumption_graph pentru anul curent."""
        poc_d = self._poc_data()
        graph = poc_d.get("consumption_graph", [])
        if not graph or not isinstance(graph, list):
            return []
        current_year = str(datetime.now().year)
        consum_key = "consum_gaz" if self._div_short == "gaz" else "consum_elec"
        result = []
        for entry in graph:
            if isinstance(entry, dict):
                month_str = entry.get("invoiced_at", "")
                if month_str.startswith(current_year):
                    val = entry.get(consum_key)
                    result.append({"month": month_str, "value": val})
        return result

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return "Licență necesară"
        entries = self._current_year_entries()
        if not entries:
            return 0
        total = 0.0
        for e in entries:
            val = e.get("value")
            if val is not None:
                try:
                    total += float(val)
                except (ValueError, TypeError):
                    pass
        return round(total, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        entries = self._current_year_entries()
        if not entries:
            return None

        unit = "m³" if self._div_short == "gaz" else "kWh"
        attrs: dict[str, Any] = {}

        for e in entries:
            month_str = e.get("month", "")
            val = e.get("value")
            # Extrage numărul lunii din "2026-01" → 1 → "Ianuarie"
            try:
                month_idx = int(month_str.split("-")[1]) - 1
                month_name = MONTHS_RO[month_idx].lower()
            except (ValueError, IndexError):
                month_name = month_str
            display_val = round(float(val), 2) if val is not None else 0
            attrs[f"Consum pe luna {month_name}"] = f"{display_val} {unit}"

        return attrs


# ═══════════════════════════════════════════════
# SENZORI PER INSTALAȚIE — ISTORIC INDEX
# ═══════════════════════════════════════════════

class MyEngieIstoricIndexSensor(MyEngieInstallationBaseSensor):
    """Index citiri — nr citiri contoare + detalii per citire.

    Entity ID: sensor.{DOMAIN}_{poc}_{div}_index_citiri_{installation}

    Datele vin din coordinator poc_data["index_history"][div_api][installation_number].

    Structura API (din captură reală browser + IndexApi.java APK):
      POST v1/index/history (JSON body)
      Body: {"autocit":"...","poc_number":"...","division":"gaz","start_date":"2023-04-01"}
      Response: json.data.istoric_citiri = [
        {"data": "24.03.2026", "index": "8197", "tip_citire": "E",
         "index_inductiva": null, "index_capacitiva": null}, ...
      ]
    """

    _attr_icon = "mdi:history"
    _attr_state_class = SensorStateClass.MEASUREMENT

    _MAX_ENTRIES = 12

    # Mapare tip_citire API → etichetă scurtă (format MyElectrica)
    _TIP_CITIRE_SHORT: dict[str, str] = {
        "autocitire aplicație mobilă": "autocitit",
        "autocitire aplicatie mobila": "autocitit",
        "autocitire": "autocitit",
        "citire reprezentant distribuitor": "citit distribuitor",
        "estimare convenție consum": "estimat",
        "estimare conventie consum": "estimat",
    }

    def __init__(self, coordinator, poc, div_short, div_label,
                 installation_number: str, pod: str = "", serie_contor: str = ""):
        super().__init__(coordinator, poc, div_short, div_label, installation_number, pod)
        self._serie_contor = serie_contor
        self._attr_unique_id = f"{DOMAIN}_{poc}_{div_short}_index_citiri_{installation_number}"
        self._attr_name = "Istoric citiri"
        self._custom_entity_id = f"sensor.{DOMAIN}_{poc}_{div_short}_istoric_citiri_{installation_number}"

    def _get_history_entries(self) -> list[dict]:
        """Returnează ultimele 12 citiri istorice pentru această instalație."""
        poc_d = self._poc_data()
        div_api = _division_api_type(self._div_short)
        inst_data = poc_d.get("index_history", {}).get(div_api, {}).get(self._installation_number)

        if inst_data is None:
            return []

        entries: list[dict] = []
        if isinstance(inst_data, dict):
            raw = inst_data.get("istoric_citiri", [])
            if isinstance(raw, list):
                entries = [e for e in raw if isinstance(e, dict)]
        elif isinstance(inst_data, list):
            entries = [e for e in inst_data if isinstance(e, dict)]

        return entries[:self._MAX_ENTRIES]

    def _short_tip(self, tip_raw: str) -> str:
        """Convertește tip_citire complet → etichetă scurtă."""
        if not tip_raw:
            return ""
        return self._TIP_CITIRE_SHORT.get(tip_raw.lower().strip(), tip_raw)

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return "Licență necesară"
        entries = self._get_history_entries()
        return len(entries) if entries else 0

    @property
    def native_unit_of_measurement(self) -> str | None:
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        entries = self._get_history_entries()
        if not entries:
            return {
                "Serie contor": self._serie_contor or "N/A",
                "Total citiri": "0",
                "attribution": ATTRIBUTION,
            }

        attrs: dict[str, Any] = {}

        for entry in entries:
            date_str = entry.get("data", "")
            index_val = entry.get("index", "")
            tip = entry.get("tip_citire", "")

            date_ro = _format_date_ro(date_str) if date_str else "N/A"
            tip_short = self._short_tip(tip)

            # Format MyElectrica: "Index (tip) DATA": "valoare"
            if tip_short:
                label = f"Index ({tip_short}) {date_ro}"
            else:
                label = f"Index {date_ro}"

            attrs[label] = str(index_val) if index_val else "N/A"

        attrs["Total citiri"] = str(len(entries))
        attrs["attribution"] = ATTRIBUTION
        return attrs


# ═══════════════════════════════════════════════
# SENZOR — DATE CONTRACT (PER UTILITATE)
# ═══════════════════════════════════════════════

class MyEngieContractSensor(MyEngieBaseSensor):
    """Date contract — status + detalii contract per utilitate.

    Entity ID: sensor.{DOMAIN}_{poc}_{div}_date_contract

    Datele vin din coordinator data["contracts"] (GET /v1/contracts).
    Structura: [{pa, poc_number, contracts: [{from_date, to_date, status,
                 contract_number, division, installation_number, ...}]}]
    """

    _attr_icon = "mdi:file-sign"

    def __init__(self, coordinator, poc, div_short, div_label):
        super().__init__(coordinator, poc, div_short, div_label)
        self._div_api = _division_api_type(div_short)
        self._attr_unique_id = f"{DOMAIN}_{poc}_{div_short}_date_contract"
        self._attr_name = "Date contract"
        self._custom_entity_id = f"sensor.{DOMAIN}_{poc}_{div_short}_date_contract"

    def _find_contract(self) -> dict | None:
        """Găsește contractul activ pentru acest POC și division."""
        data = self.coordinator.data or {}
        contracts_list = data.get("contracts", [])
        if not contracts_list or not isinstance(contracts_list, list):
            return None

        for entry in contracts_list:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("poc_number", "")) != self._poc:
                continue
            for contract in entry.get("contracts", []):
                if isinstance(contract, dict) and contract.get("division") == self._div_api:
                    return contract
        return None

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return "Licență necesară"
        contract = self._find_contract()
        if contract:
            raw_status = contract.get("status", "Necunoscut")
            return raw_status.capitalize() if isinstance(raw_status, str) else raw_status
        return "Nedefinit"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        contract = self._find_contract()
        if not contract:
            return {"attribution": ATTRIBUTION}

        attrs: dict[str, Any] = {}
        attrs["Nr. contract"] = str(contract.get("contract_number", ""))
        attrs["Descriere"] = contract.get("description", "")
        attrs["Început contract"] = _format_date_ro(contract.get("from_date", ""))
        attrs["Sfârșit contract"] = _format_date_ro(contract.get("to_date", ""))
        raw_st = contract.get("status", "")
        attrs["Status"] = raw_st.capitalize() if isinstance(raw_st, str) else raw_st
        attrs["Nr. cont contract"] = str(contract.get("contract_account_number", ""))
        attrs["Nr. instalație"] = str(contract.get("installation_number", ""))
        attrs["Division"] = contract.get("division", "")
        attrs["Document disponibil"] = "Da" if contract.get("hasDocument") else "Nu"
        attrs["attribution"] = ATTRIBUTION
        return attrs


# ═══════════════════════════════════════════════
# SENZOR — DATE UTILIZATOR (PER POC)
# ═══════════════════════════════════════════════

class MyEngieDateUtilizatorSensor(MyEngieBaseSensor):
    """Date utilizator (titular contract) — nume, contact, adresă.

    Entity ID: sensor.{DOMAIN}_{poc}_{div}_date_utilizator

    Datele vin din coordinator data["partner_details"] (GET /v1/partner/details).
    Structura: [{pa, lastName, firstName, cnp_cui, type, partnerEmail,
                 partnerMobile, addresses: [{inline, ...}]}]
    """

    _attr_icon = "mdi:account-details"

    def __init__(self, coordinator, poc, div_short, div_label, pa: str = ""):
        super().__init__(coordinator, poc, div_short, div_label)
        self._pa = pa
        self._attr_unique_id = f"{DOMAIN}_{poc}_{div_short}_date_utilizator"
        self._attr_name = "Date utilizator"
        self._custom_entity_id = f"sensor.{DOMAIN}_{poc}_{div_short}_date_utilizator"

    def _find_partner(self) -> dict | None:
        """Găsește datele partenerului pentru PA-ul acest POC."""
        data = self.coordinator.data or {}
        partner_list = data.get("partner_details", [])
        if not partner_list or not isinstance(partner_list, list):
            return None

        # Caută partenerul cu PA-ul potrivit
        if self._pa:
            for partner in partner_list:
                if isinstance(partner, dict) and str(partner.get("pa", "")) == self._pa:
                    return partner

        # Fallback: primul partener disponibil
        if partner_list and isinstance(partner_list[0], dict):
            return partner_list[0]
        return None

    @property
    def native_value(self) -> Any:
        if not self._license_valid:
            return "Licență necesară"
        partner = self._find_partner()
        if partner:
            first = partner.get("firstName", "")
            last = partner.get("lastName", "")
            return f"{first} {last}".strip() or "Necunoscut"
        return "Nedefinit"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._license_valid:
            return None
        partner = self._find_partner()
        if not partner:
            return {"attribution": ATTRIBUTION}

        attrs: dict[str, Any] = {}
        attrs["Nume"] = partner.get("lastName", "")
        attrs["Prenume"] = partner.get("firstName", "")
        attrs["Tip cont"] = "Persoană fizică" if partner.get("type") == "persoana_fizica" else partner.get("type", "")
        attrs["Email"] = partner.get("partnerEmail", "")
        attrs["Telefon mobil"] = partner.get("partnerMobile", "") or "N/A"
        attrs["Telefon fix"] = partner.get("partnerPhone", "") or "N/A"
        attrs["PA"] = str(partner.get("pa", ""))

        # Adresă inline din primul element addresses
        addresses = partner.get("addresses", [])
        if addresses and isinstance(addresses, list) and isinstance(addresses[0], dict):
            attrs["Adresă"] = addresses[0].get("inline", "")
        else:
            attrs["Adresă"] = "N/A"

        attrs["attribution"] = ATTRIBUTION
        return attrs
