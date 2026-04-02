"""DataUpdateCoordinator pentru MyENGIE România (Engie Romania).

Un singur coordinator per config_entry. Extrage TOATE datele disponibile
pentru TOATE POC-urile (places of consumption) pe care utilizatorul are acces:

  1. Login → se obțin utilizatorul și POC-urile
  2. Pentru fiecare POC:
     - Extrage PA (partner account), contract accounts, divisions (gaz/elec)
     - Pentru fiecare división: index readings, prognosis per installation
     - Balance details, invoices history, simplified inspections
     - Consumption graph, payment history (heavy refresh), green bill status

Structura returnată:
  {
      "pocs_data": {
          "5001464750": {
              "poc_number": "5001464750",
              "pa": "191207843357",
              "address": {...},
              "contract_accounts": [...],
              "divisions": {"gaz": [...], "elec": [], "details": {...}},
              "index_readings": {"gaz": [...], "elec": [...]},
              "prognosis": {"4001573662": {"01": 12, ...}},
              "balance": {"total": "0.00", "invoices": [], "pending": []},
              "invoices": [...],
              "payments": [...],
              "inspection": {"DGSIFILI0000260036": {...}},
              "consumption_graph": [...],
              "green_bill": {"has_greenbill": true, ...},
          }
      },
      "user_profile": {...},
      "current_month_key": "april",
  }
"""

import asyncio
import logging
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MyEngieApiClient
from .const import DEFAULT_UPDATE_INTERVAL, HEAVY_UPDATE_MULTIPLIER, MONTHS_EN

_LOGGER = logging.getLogger(__name__)


class MyEngieCoordinator(DataUpdateCoordinator):
    """Coordinator unic per utilizator MyENGIE România — extrage date pe POC."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: MyEngieApiClient,
        config_entry: ConfigEntry,
        update_interval: int = DEFAULT_UPDATE_INTERVAL,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"MyENGIE_{config_entry.entry_id[:8]}",
            update_interval=timedelta(seconds=update_interval),
        )
        self.api = api_client
        self.api_client = api_client  # Alias — button.py îl referă ca api_client
        self.config_entry = config_entry
        self._refresh_count: int = 0
        self._last_persisted_token: str | None = None

    @property
    def _is_heavy(self) -> bool:
        return self._refresh_count % HEAVY_UPDATE_MULTIPLIER == 0

    # ──────────────────────────────────────────
    # Fetch per POC
    # ──────────────────────────────────────────

    async def _fetch_poc_data(self, poc_number: str, pa: str, is_heavy: bool) -> dict:
        """Extrage toate datele pentru un POC (place of consumption).

        Args:
            poc_number: Codul POC (de ex. "5001464750")
            pa: Partner Account clientId
            is_heavy: True dacă este heavy refresh (fetch date suplimentare)

        Returns:
            Dict cu datele POC: divisions, index readings, prognosis, balance, etc.
        """
        prev = self.data or {}
        prev_poc = prev.get("pocs_data", {}).get(poc_number, {})

        # ── 1. Divisions (gaz/elec) ──
        try:
            divisions_data = await self.api.async_get_divisions(poc_number, pa)
        except Exception as err:
            _LOGGER.warning("[MyENGIE] Eroare la divisions POC %s: %s", poc_number, err)
            divisions_data = {"gaz": [], "elec": [], "details": {}}

        gaz_insts = divisions_data.get("gaz", [])
        elec_insts = divisions_data.get("elec", [])
        divisions_details = divisions_data.get("details", {})

        # ── 2. Index readings per división ──
        index_readings = {"gaz": [], "elec": []}

        # Fetch gaz readings (paralel)
        gaz_tasks = []
        for inst_nr in gaz_insts:
            gaz_tasks.append(
                self.api.async_get_index_readings(poc_number, "gaz", pa, inst_nr)
            )

        if gaz_tasks:
            gaz_results = await asyncio.gather(*gaz_tasks, return_exceptions=True)
            for inst_nr, result in zip(gaz_insts, gaz_results):
                if isinstance(result, Exception):
                    _LOGGER.warning(
                        "[MyENGIE] Eroare la index readings gaz POC %s inst %s: %s",
                        poc_number, inst_nr, result,
                    )
                elif result:
                    index_readings["gaz"].append(result)

        # Fetch elec readings (paralel)
        elec_tasks = []
        for inst_nr in elec_insts:
            elec_tasks.append(
                self.api.async_get_index_readings(poc_number, "elec", pa, inst_nr)
            )

        if elec_tasks:
            elec_results = await asyncio.gather(*elec_tasks, return_exceptions=True)
            for inst_nr, result in zip(elec_insts, elec_results):
                if isinstance(result, Exception):
                    _LOGGER.warning(
                        "[MyENGIE] Eroare la index readings elec POC %s inst %s: %s",
                        poc_number, inst_nr, result,
                    )
                elif result:
                    index_readings["elec"].append(result)

        # ── 2b. Index history per installation (POST v1/index/history) ──
        # Necesită autocit + serie_contor din index_readings (deja obținute la pas 2)
        index_history: dict[str, dict] = {"gaz": {}, "elec": {}}

        def _extract_inst_info(readings_list: list, div_key: str) -> dict[str, dict]:
            """Extrage autocit și serie_contor per installation_number din index_readings."""
            info: dict[str, dict] = {}
            for item in readings_list:
                if isinstance(item, dict):
                    for inst in item.get("installations", []):
                        if isinstance(inst, dict):
                            inst_str = str(inst.get("installation_number", ""))
                            if inst_str:
                                info[inst_str] = {
                                    "autocit": str(inst.get("autocit", "")),
                                    "serie_contor": str(inst.get("serie_contor", "")),
                                }
                elif isinstance(item, list):
                    for sub in item:
                        if isinstance(sub, dict):
                            for inst in sub.get("installations", []):
                                if isinstance(inst, dict):
                                    inst_str = str(inst.get("installation_number", ""))
                                    if inst_str:
                                        info[inst_str] = {
                                            "autocit": str(inst.get("autocit", "")),
                                            "serie_contor": str(inst.get("serie_contor", "")),
                                        }
            return info

        # serie_contor fallback din divisions_details
        def _get_serie(inst_nr_str: str) -> str:
            for _key, detail in divisions_details.items():
                if isinstance(detail, dict) and str(detail.get("installation_number", "")) == inst_nr_str:
                    return str(detail.get("serie_contor", detail.get("meterSerial", "")))
            return ""

        gaz_inst_info = _extract_inst_info(index_readings.get("gaz", []), "gaz")
        elec_inst_info = _extract_inst_info(index_readings.get("elec", []), "elec")

        # Fetch gaz index history
        gaz_hist_tasks = []
        for inst_nr in gaz_insts:
            inst_str = str(inst_nr)
            inst_data = gaz_inst_info.get(inst_str, {})
            autocit = inst_data.get("autocit", "")
            serie = inst_data.get("serie_contor", "") or _get_serie(inst_str)
            gaz_hist_tasks.append(
                self.api.async_get_index_history(
                    poc_number, pa, "gaz",
                    installation_number=inst_str,
                    serie_contor=serie,
                    autocit=autocit,
                )
            )

        if gaz_hist_tasks:
            gaz_hist_results = await asyncio.gather(*gaz_hist_tasks, return_exceptions=True)
            for inst_nr, result in zip(gaz_insts, gaz_hist_results):
                if isinstance(result, Exception):
                    _LOGGER.warning(
                        "[MyENGIE] Eroare la index history gaz POC %s inst %s: %s",
                        poc_number, inst_nr, result,
                    )
                elif result is not None:
                    index_history["gaz"][str(inst_nr)] = result

        # Fetch elec index history
        elec_hist_tasks = []
        for inst_nr in elec_insts:
            inst_str = str(inst_nr)
            inst_data = elec_inst_info.get(inst_str, {})
            autocit = inst_data.get("autocit", "")
            serie = inst_data.get("serie_contor", "") or _get_serie(inst_str)
            elec_hist_tasks.append(
                self.api.async_get_index_history(
                    poc_number, pa, "elec",
                    installation_number=inst_str,
                    serie_contor=serie,
                    autocit=autocit,
                )
            )

        if elec_hist_tasks:
            elec_hist_results = await asyncio.gather(*elec_hist_tasks, return_exceptions=True)
            for inst_nr, result in zip(elec_insts, elec_hist_results):
                if isinstance(result, Exception):
                    _LOGGER.warning(
                        "[MyENGIE] Eroare la index history elec POC %s inst %s: %s",
                        poc_number, inst_nr, result,
                    )
                elif result is not None:
                    index_history["elec"][str(inst_nr)] = result

        # ── 3. Prognosis per installation ──
        prognosis = {}

        # Gaz prognosis
        gaz_prog_tasks = []
        for inst_nr in gaz_insts:
            gaz_prog_tasks.append(
                self.api.async_get_prognosis(poc_number, inst_nr, pa)
            )

        if gaz_prog_tasks:
            gaz_prog_results = await asyncio.gather(
                *gaz_prog_tasks, return_exceptions=True
            )
            for inst_nr, result in zip(gaz_insts, gaz_prog_results):
                if isinstance(result, Exception):
                    _LOGGER.warning(
                        "[MyENGIE] Eroare la prognosis gaz POC %s inst %s: %s",
                        poc_number, inst_nr, result,
                    )
                elif result:
                    prognosis[inst_nr] = result

        # Elec prognosis
        elec_prog_tasks = []
        for inst_nr in elec_insts:
            elec_prog_tasks.append(
                self.api.async_get_prognosis(poc_number, inst_nr, pa)
            )

        if elec_prog_tasks:
            elec_prog_results = await asyncio.gather(
                *elec_prog_tasks, return_exceptions=True
            )
            for inst_nr, result in zip(elec_insts, elec_prog_results):
                if isinstance(result, Exception):
                    _LOGGER.warning(
                        "[MyENGIE] Eroare la prognosis elec POC %s inst %s: %s",
                        poc_number, inst_nr, result,
                    )
                elif result:
                    prognosis[inst_nr] = result

        # ── 4. Fetch date esențiale (paralel) ──
        # Balance details — necesită lista de contract_account_numbers
        contract_account_numbers = []
        for poc_raw in (self.data or {}).get("_raw_pocs", []):
            if str(poc_raw.get("poc_number", "")) == poc_number:
                for cc in poc_raw.get("cont_contract", []):
                    ca_nr = cc.get("contract_account_number")
                    if ca_nr:
                        contract_account_numbers.append(int(ca_nr))
                break
        if not contract_account_numbers:
            # Fallback: extrage din divisions_data dacă există
            for _key, detail in divisions_details.items():
                if isinstance(detail, dict):
                    ca_nr = detail.get("contract_account_number")
                    if ca_nr and int(ca_nr) not in contract_account_numbers:
                        contract_account_numbers.append(int(ca_nr))

        # Consumption graph — ultimele 12 luni
        from datetime import datetime as _dt
        now = _dt.now()
        start_date = f"{now.year - 1}-{now.month:02d}-01"
        end_date = f"{now.year}-{now.month:02d}-{now.day:02d}"

        essential_tasks = [
            self.api.async_get_invoices_history(poc_number, pa),
            self.api.async_get_consumption_graph(poc_number, pa, start_date, end_date),
        ]

        essential = await asyncio.gather(*essential_tasks, return_exceptions=True)
        invoices = essential[0] if not isinstance(essential[0], Exception) else []
        consumption_graph = essential[1] if not isinstance(essential[1], Exception) else []

        for task_name, result in [
            ("invoices_history", essential[0]),
            ("consumption_graph", essential[1]),
        ]:
            if isinstance(result, Exception):
                _LOGGER.warning(
                    "[MyENGIE] Eroare la %s POC %s: %s", task_name, poc_number, result
                )

        # Balance details — apel separat (necesită contract_accounts)
        balance = {"total": "0.00", "invoices": [], "pending": []}
        if contract_account_numbers:
            try:
                balance_result = await self.api.async_get_balance_details(contract_account_numbers)
                if balance_result:
                    balance = balance_result
            except Exception as err:
                _LOGGER.warning("[MyENGIE] Eroare la balance_details POC %s: %s", poc_number, err)

        # ── 5. Payment history și green bill (doar la heavy refresh) ──
        payments = []
        green_bill = {}

        if is_heavy:
            try:
                # Transmitem date range (an curent) — unele API-uri Engie necesită
                pay_start = f"{now.year}-01-01"
                pay_end = f"{now.year}-{now.month:02d}-{now.day:02d}"
                payments = await self.api.async_get_payment_history(
                    pa, start_date=pay_start, end_date=pay_end
                )
                if payments is None:
                    payments = prev_poc.get("payments", [])
            except Exception as err:
                _LOGGER.warning("[MyENGIE] Eroare la payment history POC %s: %s", poc_number, err)
                payments = prev_poc.get("payments", [])

            try:
                green_bill = await self.api.async_get_green_bill_status(poc_number, pa)
            except Exception as err:
                _LOGGER.warning("[MyENGIE] Eroare la green bill POC %s: %s", poc_number, err)
                green_bill = prev_poc.get("green_bill", {})
        else:
            # Light refresh — preiau de la cached data
            payments = prev_poc.get("payments", [])
            green_bill = prev_poc.get("green_bill", {})

        # ── 6. Simplified inspections per POD ──
        inspection_data = {}

        if divisions_details:
            inspection_tasks = []
            pod_codes = []

            # divisions_details e un dict keyed "{inst}_{serial}" cu valori care au "pod"
            for _key, detail in divisions_details.items():
                if isinstance(detail, dict):
                    pod_code = detail.get("pod", "")
                    if pod_code and pod_code not in pod_codes:
                        pod_codes.append(pod_code)
                        inspection_tasks.append(
                            self.api.async_get_simplified_inspection(poc_number, pod_code, pa)
                        )

            if inspection_tasks:
                inspection_results = await asyncio.gather(
                    *inspection_tasks, return_exceptions=True
                )
                for pod_code, result in zip(pod_codes, inspection_results):
                    if isinstance(result, Exception):
                        _LOGGER.warning(
                            "[MyENGIE] Eroare la simplified inspection POC %s pod %s: %s",
                            poc_number, pod_code, result,
                        )
                    elif result:
                        inspection_data[pod_code] = result

        _LOGGER.debug(
            "[MyENGIE] Fetch POC %s (PA %s): gaz=%d, elec=%d, instalații=%d, "
            "facturi=%d, balanță=%s, inspecții=%d",
            poc_number, pa,
            len(gaz_insts), len(elec_insts),
            len(gaz_insts) + len(elec_insts),
            len(invoices),
            balance.get("total", "?"),
            len(inspection_data),
        )

        return {
            "poc_number": poc_number,
            "pa": pa,
            "address": divisions_data.get("address", {}),
            "contract_accounts": divisions_data.get("contract_accounts", []),
            "divisions": {
                "gaz": gaz_insts,
                "elec": elec_insts,
                "details": divisions_details,
            },
            "index_readings": index_readings,
            "index_history": index_history,
            "prognosis": prognosis,
            "balance": balance,
            "invoices": invoices,
            "payments": payments,
            "inspection": inspection_data,
            "consumption_graph": consumption_graph,
            "green_bill": green_bill,
        }

    # ──────────────────────────────────────────
    # Update principal — multi-POC
    # ──────────────────────────────────────────

    async def _async_update_data(self) -> dict:
        """Extrage toate datele de la API-ul MyENGIE România pentru TOATE POC-urile."""
        is_heavy = self._is_heavy
        _LOGGER.debug(
            "[MyENGIE] Actualizare (refresh=#%s, tip=%s)",
            self._refresh_count, "HEAVY" if is_heavy else "light",
        )

        try:
            # ── 1. Asigurăm autentificarea ──
            if not await self.api.async_ensure_authenticated():
                raise UpdateFailed(
                    "[MyENGIE] Autentificare eșuată — verifică credențialele "
                    "sau dacă serverul Engie este în mentenanță"
                )

            # ── 2. Date globale (profil, contracte, partner) — paralel ──
            user_profile = None
            contracts_data = []
            partner_details = []

            try:
                global_tasks = [
                    self.api.async_get_user_profile(),
                    self.api.async_get_contracts(),
                    self.api.async_get_partners(""),
                ]
                global_results = await asyncio.gather(*global_tasks, return_exceptions=True)

                if not isinstance(global_results[0], Exception):
                    user_profile = global_results[0]
                else:
                    _LOGGER.warning("[MyENGIE] Eroare la user profile: %s", global_results[0])

                if not isinstance(global_results[1], Exception) and global_results[1]:
                    contracts_data = global_results[1]
                else:
                    if isinstance(global_results[1], Exception):
                        _LOGGER.warning("[MyENGIE] Eroare la contracts: %s", global_results[1])

                if not isinstance(global_results[2], Exception) and global_results[2]:
                    partner_details = global_results[2]
                else:
                    if isinstance(global_results[2], Exception):
                        _LOGGER.warning("[MyENGIE] Eroare la partner details: %s", global_results[2])

            except Exception as err:
                _LOGGER.warning("[MyENGIE] Eroare la date globale: %s", err)

            # ── 3. POC-uri (places of consumption) ──
            pocs_list = []
            try:
                cp_data = await self.api.async_get_consumption_places()
                if cp_data and isinstance(cp_data, dict):
                    pocs_list = cp_data.get("places_of_consumption", []) or []
                elif cp_data and isinstance(cp_data, list):
                    pocs_list = cp_data
            except Exception as err:
                _LOGGER.warning("[MyENGIE] Eroare la consumption places: %s", err)
                raise UpdateFailed(f"[MyENGIE] Nu s-au putut obține POC-urile: {err}") from err

            if not pocs_list:
                _LOGGER.warning("[MyENGIE] Niciun POC disponibil pentru utilizator")

            current_month_key = MONTHS_EN[datetime.now().month - 1]

            # ── 4. Fetch date pentru fiecare POC (paralel) ──
            pocs_data: dict[str, dict] = {}
            poc_tasks = []
            poc_infos = []

            for poc in pocs_list:
                poc_number = str(poc.get("poc_number", "")).strip()
                pa = str(poc.get("pa", "")).strip()

                if not poc_number or not pa:
                    _LOGGER.warning("[MyENGIE] POC fără poc_number sau pa: %s", poc)
                    continue

                poc_infos.append((poc_number, pa))
                poc_tasks.append(self._fetch_poc_data(poc_number, pa, is_heavy))

            if poc_tasks:
                results = await asyncio.gather(*poc_tasks, return_exceptions=True)
                for (poc_number, pa), result in zip(poc_infos, results):
                    if isinstance(result, Exception):
                        _LOGGER.warning(
                            "[MyENGIE] Eroare la fetch POC %s (PA %s): %s",
                            poc_number, pa, result,
                        )
                    else:
                        pocs_data[poc_number] = result

            # ── 5. Incrementăm counter și persistăm token ──
            self._refresh_count += 1
            self._persist_token()

            total_divisions = sum(
                len(p.get("divisions", {}).get("gaz", []))
                + len(p.get("divisions", {}).get("elec", []))
                for p in pocs_data.values()
            )
            _LOGGER.debug(
                "[MyENGIE] Actualizare finalizată: %d POC-uri, %d instalații gaz+elec",
                len(pocs_data), total_divisions,
            )

            return {
                # Date per POC
                "pocs_data": pocs_data,

                # Date globale
                "user_profile": user_profile,
                "contracts": contracts_data,
                "partner_details": partner_details,
                "current_month_key": current_month_key,

                # Raw POC data (pentru coordinator la refresh viitoare)
                "_raw_pocs": pocs_list,
            }

        except UpdateFailed:
            raise
        except Exception as err:
            _LOGGER.exception("[MyENGIE] Eroare la actualizare: %s", err)
            raise UpdateFailed(f"[MyENGIE] Eroare la actualizare: {err}") from err

    def _persist_token(self) -> None:
        """Salvează token-ul în config_entry doar dacă s-a schimbat."""
        token_data = self.api.export_token_data()
        if not token_data or not self.config_entry:
            return

        current_token = token_data.get("token")
        if current_token == self._last_persisted_token:
            return  # Nu s-a schimbat — evităm scrieri inutile

        new_data = dict(self.config_entry.data)
        new_data["token_data"] = token_data
        self.hass.config_entries.async_update_entry(
            self.config_entry, data=new_data
        )
        self._last_persisted_token = current_token
