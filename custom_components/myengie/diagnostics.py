"""
Diagnosticare pentru integrarea MyENGIE România (Engie Romania).

Exportă informații de diagnostic pentru support tickets:
- Licență (fingerprint, status, cheie mascată)
- Starea coordinator-ului
- Senzori, butoane active

Datele sensibile (parolă, token-uri) sunt excluse.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, LICENSE_DATA_KEY


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Returnează datele de diagnostic pentru MyENGIE România."""

    # ── Licență (fingerprint + cheie mascată) ──
    license_mgr = hass.data.get(DOMAIN, {}).get(LICENSE_DATA_KEY)
    licenta_info: dict[str, Any] = {}
    if license_mgr:
        licenta_info = {
            "fingerprint": license_mgr.fingerprint,
            "status": license_mgr.status,
            "license_key": license_mgr.license_key_masked,
            "is_valid": license_mgr.is_valid,
            "license_type": license_mgr.license_type,
        }

    # ── Coordinator (via runtime_data) ──
    runtime = getattr(entry, "runtime_data", None)
    coordinator_info: dict[str, Any] = {}
    if runtime and hasattr(runtime, "coordinator") and runtime.coordinator:
        coordinator = runtime.coordinator
        coordinator_info = {
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
        }
        data = coordinator.data or {}
        pocs_data = data.get("pocs_data", {})
        coordinator_info["pocs_count"] = len(pocs_data)

        # Sumar per POC
        pocs_summary = {}
        for poc_nr, poc_data in pocs_data.items():
            divisions = poc_data.get("divisions", {})
            payments_raw = poc_data.get("payments")
            payments_count = len(payments_raw) if isinstance(payments_raw, list) else 0
            pocs_summary[poc_nr] = {
                "pa": poc_data.get("pa", ""),
                "gaz_installations": len(divisions.get("gaz", [])),
                "elec_installations": len(divisions.get("elec", [])),
                "invoices_count": len(poc_data.get("invoices", [])),
                "payments_count": payments_count,
                "balance_total": poc_data.get("balance", {}).get("total", "?"),
                "index_history_gaz": len(poc_data.get("index_history", {}).get("gaz", {})),
                "index_history_elec": len(poc_data.get("index_history", {}).get("elec", {})),
                "consumption_months": len(poc_data.get("consumption_graph", [])),
            }
        coordinator_info["pocs_summary"] = pocs_summary

        # Date globale
        contracts_raw = data.get("contracts", [])
        partner_raw = data.get("partner_details", [])
        coordinator_info["contracts_count"] = len(contracts_raw) if isinstance(contracts_raw, list) else 0
        coordinator_info["partner_details_count"] = len(partner_raw) if isinstance(partner_raw, list) else 0

    # ── Senzori activi ──
    senzori_activi = sorted(
        entitate.entity_id
        for entitate in hass.states.async_all("sensor")
        if entitate.entity_id.startswith(f"sensor.{DOMAIN}_")
    )

    # ── Butoane active ──
    butoane_active = sorted(
        entitate.entity_id
        for entitate in hass.states.async_all("button")
        if entitate.entity_id.startswith(f"button.{DOMAIN}_")
    )

    # ── Config entry (fără date sensibile) ──
    return {
        "intrare": {
            "titlu": entry.title,
            "versiune": entry.version,
            "domeniu": DOMAIN,
            "username": _mascheaza_email(entry.data.get("username", "")),
            "update_interval": entry.data.get("update_interval"),
        },
        "licenta": licenta_info,
        "coordinator": coordinator_info,
        "stare": {
            "senzori_activi": len(senzori_activi),
            "lista_senzori": senzori_activi,
            "butoane_active": len(butoane_active),
            "lista_butoane": butoane_active,
        },
    }


def _mascheaza_email(email: str) -> str:
    """Maschează email-ul păstrând prima literă și domeniul."""
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 1:
        return f"*@{domain}"
    return f"{local[0]}{'*' * (len(local) - 1)}@{domain}"
