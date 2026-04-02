"""Client API pentru MyENGIE România (Engie Romania).

Bazat pe debug_myengie.py (funcțional 100%) — parametri și opțiuni identice.
Toate endpoint-urile sunt validate cu răspunsuri reale din debug script.

IMPORTANT — Particularități Engie API:
  1. Login: POST form-urlencoded (NU JSON)
  2. Răspunsul login conține {data: {token, refresh_token, id_token, exp}}
  3. Câmpul se numește "token" (NU "access_token")
  4. După login, request-urile autentificate folosesc Content-Type: application/json
  5. Serverul poate returna Content-Type: text/html cu body JSON valid
     → se folosește resp.text() + json.loads(), NU resp.json()
  6. Device headers sunt OBLIGATORII (din DeviceInfoProvider.java)
"""

import asyncio
import json
import logging
import time
from typing import Any
from urllib.parse import urlencode

from aiohttp import ClientSession, ClientTimeout

from .const import (
    API_BASE,
    API_TIMEOUT,
    DEVICE_HEADERS,
    HEADERS_BASE,
    OAUTH_AUDIENCE,
    OAUTH_CLIENT_ID,
    TOKEN_MAX_AGE,
    TOKEN_REFRESH_THRESHOLD,
    URL_LOGIN,
    URL_NOTIFICATIONS,
    URL_NOTIFICATIONS_UNREAD,
    URL_OAUTH_TOKEN,
    URL_USER_ME,
    URL_CONSUMPTION_PLACES,
)

_LOGGER = logging.getLogger(__name__)


class MyEngieApiClient:
    """Client API pentru MyENGIE România (Engie Romania).

    Pattern identic cu debug_myengie.py:
    - Login: form-urlencoded, headere session-like
    - Requests autentificate: Content-Type: application/json, Bearer token
    - Parsare JSON: text() + json.loads() (serverul returnează text/html uneori)
    """

    def __init__(self, session: ClientSession, email: str, password: str) -> None:
        self._session = session
        self._email = email
        self._password = password

        # Token
        self._token: str | None = None
        self._refresh_token: str | None = None
        self._id_token: str | None = None
        self._token_obtained_at: float = 0.0
        self._token_expires_in: int = TOKEN_MAX_AGE
        self._auth_lock = asyncio.Lock()

        # User data din login
        self._user_data: dict | None = None
        self._crm_account: str | None = None  # Partner Account (PA/clientId)

        self._timeout = ClientTimeout(total=API_TIMEOUT)

    # ──────────────────────────────────────────
    # Proprietăți
    # ──────────────────────────────────────────

    @property
    def crm_account(self) -> str | None:
        """Partner Account (PA/clientId) — ID-ul partenerului din MyENGIE România."""
        return self._crm_account

    @property
    def user_data(self) -> dict | None:
        """Payload-ul complet din login."""
        return self._user_data

    @property
    def has_token(self) -> bool:
        return self._token is not None

    def is_token_valid(self) -> bool:
        """Verifică dacă token-ul e valid (există și nu a expirat).

        Identic cu APK UserTokenProvider.isTokenValid():
            Instant.now().plus(2, MINUTES).getEpochSecond() <= token.validUntil
        Noi folosim un buffer de TOKEN_REFRESH_THRESHOLD (5 min) ca marjă de siguranță.
        """
        if not self._token:
            return False
        age = time.monotonic() - self._token_obtained_at
        return age < (self._token_expires_in - TOKEN_REFRESH_THRESHOLD)

    def _invalidate_token(self) -> None:
        """Marchează token-ul curent ca invalid (forțează re-auth la next request)."""
        self._token_obtained_at = 0.0

    # ──────────────────────────────────────────
    # Headers — identic cu debug_myengie.py
    # ──────────────────────────────────────────

    def _login_headers(self) -> dict[str, str]:
        """Headere pentru login — form-urlencoded + device headers.

        Exact ca în debug_myengie.py.__init__():
            session.headers = {Accept, Content-Type: form, source, App-Version, ...}
        """
        headers = dict(HEADERS_BASE)
        headers.update(DEVICE_HEADERS)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        return headers

    def _auth_headers(self) -> dict[str, str]:
        """Headere pentru request-uri autentificate — JSON + Bearer token.

        Exact ca în debug_myengie.py login() success path:
            session.headers["Authorization"] = f"Bearer {access_token}"
            session.headers["Content-Type"] = "application/json"
        """
        headers = dict(HEADERS_BASE)
        headers.update(DEVICE_HEADERS)
        headers["Content-Type"] = "application/json"
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    # ──────────────────────────────────────────
    # JSON parsing — safe, ca requests.Response.json()
    # ──────────────────────────────────────────

    async def _parse_json(self, resp) -> Any:
        """Parsează răspunsul ca JSON, tolerant la Content-Type greșit.

        Serverul Engie returnează uneori Content-Type: text/html cu body JSON valid.
        requests.Response.json() folosește simplu json.loads(text) fără verificare.
        Facem la fel: citim text, parsăm cu json.loads().
        """
        try:
            text = await resp.text(encoding="utf-8")
        except Exception:
            text = await resp.text()

        if not text or not text.strip():
            return None

        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            # Detecție mentenanță Engie (returnează HTML cu status 200)
            if "indisponibil" in text[:500] or "mentenan" in text[:500].lower():
                _LOGGER.warning(
                    "[MyENGIE] Serverul Engie este în MENTENANȚĂ — "
                    "răspuns HTML în loc de JSON de la %s",
                    resp.url,
                )
            else:
                _LOGGER.warning(
                    "[MyENGIE] Răspuns non-JSON de la %s (status=%s, content-type=%s): %s...",
                    resp.url,
                    resp.status,
                    resp.headers.get("Content-Type", "?"),
                    text[:200],
                )
            return None

    # ──────────────────────────────────────────
    # Autentificare — identic cu debug_myengie.py
    # ──────────────────────────────────────────

    # Constante rezultat login — folosite și de config_flow.py
    LOGIN_OK = "ok"
    LOGIN_AUTH_FAILED = "auth_failed"
    LOGIN_MAINTENANCE = "maintenance"
    LOGIN_NETWORK_ERROR = "network_error"
    LOGIN_UNKNOWN_ERROR = "unknown_error"

    async def _do_login(self) -> str:
        """POST /v1/login cu form-urlencoded → JWT token.

        INTERN — apelat doar din async_ensure_authenticated() sub _auth_lock.

        Returnează un string cu motivul:
            "ok"            — login reușit
            "auth_failed"   — credențiale greșite
            "maintenance"   — server în mentenanță (HTML în loc de JSON)
            "network_error" — eroare rețea / timeout
            "unknown_error" — eroare necunoscută
        """
        try:
            body_str = urlencode({
                "username": self._email,
                "password": self._password,
            })

            _LOGGER.debug(
                "Login MyENGIE: POST %s (email=%s, body_len=%d)",
                URL_LOGIN, self._email, len(body_str),
            )

            async with self._session.post(
                URL_LOGIN,
                data=body_str,
                headers=self._login_headers(),
                timeout=self._timeout,
            ) as resp:
                _LOGGER.debug(
                    "Login response: status=%s, content-type=%s",
                    resp.status,
                    resp.headers.get("Content-Type", "?"),
                )

                if resp.status != 200:
                    _LOGGER.error(
                        "Login eșuat: status=%s, email=%s",
                        resp.status, self._email,
                    )
                    return self.LOGIN_AUTH_FAILED

                data = await self._parse_json(resp)
                if data is None:
                    _LOGGER.error(
                        "[MyENGIE] Login eșuat: răspuns non-JSON (server în mentenanță). "
                        "email=%s, content-type=%s",
                        self._email,
                        resp.headers.get("Content-Type", "?"),
                    )
                    return self.LOGIN_MAINTENANCE

                if data.get("error") is True:
                    _LOGGER.error(
                        "Login eșuat: error flag în răspuns, email=%s, errors=%s",
                        self._email,
                        data.get("errors", {}),
                    )
                    return self.LOGIN_AUTH_FAILED

                # Extrage payload-ul din data.data
                payload = data.get("data", {}) or data

                # Token — "token" (NU "access_token") — conform APK AuthApiKt.toToken()
                self._token = (
                    payload.get("token")
                    or payload.get("access_token")
                    or data.get("token")
                    or data.get("access_token")
                )
                if not self._token:
                    _LOGGER.error(
                        "Login: răspuns OK dar token absent. Keys=%s",
                        list(payload.keys()) if isinstance(payload, dict) else type(payload),
                    )
                    return self.LOGIN_UNKNOWN_ERROR

                # ID Token (pentru logout: id_token_hint)
                self._id_token = payload.get("id_token") or data.get("id_token")

                # Refresh Token
                self._refresh_token = payload.get("refresh_token") or data.get("refresh_token")

                self._token_obtained_at = time.monotonic()

                # Expirare — APK: Instant.now().plusSeconds(Long.parseLong(exp)).getEpochSecond()
                # Deci exp e DURATĂ în secunde (ex: 7200), NU epoch timestamp
                exp_val = payload.get("exp") or data.get("exp")
                if exp_val:
                    try:
                        self._token_expires_in = int(exp_val)
                    except (ValueError, TypeError):
                        self._token_expires_in = TOKEN_MAX_AGE
                else:
                    self._token_expires_in = TOKEN_MAX_AGE

                # Salvăm payload-ul complet
                self._user_data = data

                _LOGGER.info(
                    "Login MyENGIE reușit: email=%s, token=%s..., exp=%ds, refresh_token=%s",
                    self._email,
                    self._token[:20] if self._token else "?",
                    self._token_expires_in,
                    "da" if self._refresh_token else "nu",
                )
                return self.LOGIN_OK

        except asyncio.TimeoutError:
            _LOGGER.error("[MyENGIE] Login timeout — server indisponibil")
            return self.LOGIN_NETWORK_ERROR
        except Exception:
            _LOGGER.exception("Eroare la login MyENGIE API")
            return self.LOGIN_UNKNOWN_ERROR

    async def async_login(self) -> str:
        """Login public — cu lock (thread-safe)."""
        async with self._auth_lock:
            return await self._do_login()

    async def _do_refresh_token(self) -> bool:
        """Refresh token via OAuth2 endpoint — identic cu APK UserTokenProvider.refreshAuthToken().

        INTERN — apelat doar din async_ensure_authenticated() sub _auth_lock.

        APK face:
            POST https://auth.engie.ro/oauth/token
            Content-Type: application/x-www-form-urlencoded
            Headers: device headers (DeviceInfoProvider)
            Body: client_id, grant_type=refresh_token, refresh_token, audience

        Response (AuthApiKt.toNewToken):
            {access_token, id_token, refresh_token, expires_in}
        """
        if not self._refresh_token:
            _LOGGER.debug("[MyENGIE] Refresh imposibil — refresh_token absent")
            return False

        try:
            headers = dict(DEVICE_HEADERS)
            headers["Content-Type"] = "application/x-www-form-urlencoded"

            body_str = urlencode({
                "client_id": OAUTH_CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "audience": OAUTH_AUDIENCE,
            })

            _LOGGER.debug(
                "[MyENGIE] Token refresh: POST %s (email=%s)",
                URL_OAUTH_TOKEN, self._email,
            )

            async with self._session.post(
                URL_OAUTH_TOKEN,
                data=body_str,
                headers=headers,
                timeout=self._timeout,
            ) as resp:
                _LOGGER.debug(
                    "[MyENGIE] Refresh response: status=%s, content-type=%s",
                    resp.status,
                    resp.headers.get("Content-Type", "?"),
                )

                if resp.status != 200:
                    _LOGGER.info(
                        "[MyENGIE] Token refresh eșuat: status=%s",
                        resp.status,
                    )
                    # Refresh token invalid/expirat — îl golim
                    if resp.status in (401, 403):
                        self._refresh_token = None
                    return False

                data = await self._parse_json(resp)
                if not data:
                    _LOGGER.warning("[MyENGIE] Refresh: răspuns gol sau non-JSON")
                    return False

                # APK AuthApiKt.toNewToken() — răspunsul OAuth2 standard:
                #   "access_token" (NU "token"), "id_token", "refresh_token", "expires_in"
                new_token = data.get("access_token")
                if not new_token:
                    _LOGGER.warning(
                        "[MyENGIE] Refresh: access_token absent. Keys=%s",
                        list(data.keys()) if isinstance(data, dict) else "?",
                    )
                    return False

                self._token = new_token
                self._id_token = data.get("id_token", self._id_token)
                # Refresh token poate fi rotit de server
                new_refresh = data.get("refresh_token")
                if new_refresh:
                    self._refresh_token = new_refresh
                self._token_obtained_at = time.monotonic()

                # expires_in = durată în secunde (ex: 7200)
                # APK: Instant.now().plusSeconds(expires_in).getEpochSecond()
                expires_in = data.get("expires_in")
                if expires_in:
                    try:
                        self._token_expires_in = int(expires_in)
                    except (ValueError, TypeError):
                        self._token_expires_in = TOKEN_MAX_AGE
                else:
                    self._token_expires_in = TOKEN_MAX_AGE

                _LOGGER.info(
                    "[MyENGIE] Token refresh reușit: email=%s, token=%s..., exp=%ds",
                    self._email,
                    self._token[:20] if self._token else "?",
                    self._token_expires_in,
                )
                return True

        except asyncio.TimeoutError:
            _LOGGER.warning("[MyENGIE] Token refresh timeout")
            return False
        except Exception:
            _LOGGER.exception("[MyENGIE] Eroare la token refresh")
            return False

    async def async_ensure_authenticated(self) -> bool:
        """Asigură un token valid — refresh token first, apoi re-login.

        Identic cu fluxul APK UserTokenProvider.checkAuthTokenValidity():
            1. Verifică is_token_valid() (cu buffer de 2 min / 5 min la noi)
            2. Dacă nu, acquire mutex (un singur refresh/login la un moment dat)
            3. Double-check după lock (altă corutină poate a rezolvat deja)
            4. Încearcă refresh_token (rapid, fără username/password)
            5. Fallback: login complet (username/password)
        """
        if self.is_token_valid():
            return True

        async with self._auth_lock:
            # Double-check după ce am obținut lock-ul
            # (altă corutină poate a făcut refresh/login între timp)
            if self.is_token_valid():
                return True

            # 1. Încearcă refresh token (rapid, fără credențiale)
            if self._refresh_token:
                _LOGGER.debug(
                    "[MyENGIE] Token expirat — încerc refresh (email=%s)",
                    self._email,
                )
                if await self._do_refresh_token():
                    return True
                _LOGGER.debug("[MyENGIE] Refresh eșuat — fallback la login complet")

            # 2. Fallback: login complet
            _LOGGER.debug(
                "[MyENGIE] Login complet (email=%s)", self._email,
            )
            result = await self._do_login()
            return result == self.LOGIN_OK

    # ──────────────────────────────────────────
    # Helpers request — identic cu debug_myengie.py _get/_post
    # ──────────────────────────────────────────

    async def _get(self, url: str, params: dict | None = None) -> Any:
        """GET request autentificat cu retry automat pe 401.

        Flux (identic cu APK EngieApiClient + ErrorInterceptor):
            1. Asigură token valid (refresh / login dacă e nevoie)
            2. Execută request-ul
            3. Dacă 401 → invalidează token → re-auth → retry O SINGURĂ DATĂ
        """
        if not await self.async_ensure_authenticated():
            return None

        for attempt in range(2):
            try:
                async with self._session.get(
                    url,
                    headers=self._auth_headers(),
                    params=params,
                    timeout=self._timeout,
                ) as resp:
                    if resp.status == 200:
                        return await self._parse_json(resp)

                    if resp.status == 401 and attempt == 0:
                        _LOGGER.debug(
                            "[MyENGIE] 401 la GET %s — invalidez token și reîncerc",
                            url,
                        )
                        self._invalidate_token()
                        if await self.async_ensure_authenticated():
                            continue  # retry cu token nou
                        _LOGGER.warning("GET %s → 401 (re-auth eșuat)", url)
                        return None

                    _LOGGER.warning("GET %s → %s", url, resp.status)
                    return None
            except Exception:
                _LOGGER.exception("Eroare GET %s", url)
                return None
        return None

    async def _post(
        self,
        url: str,
        body: dict | None = None,
        form_data: bool = False,
    ) -> Any:
        """POST request autentificat cu retry automat pe 401.

        Identic cu _get: retry o singură dată pe 401.
        """
        if not await self.async_ensure_authenticated():
            return None

        for attempt in range(2):
            try:
                headers = self._auth_headers()

                if form_data:
                    headers["Content-Type"] = "application/x-www-form-urlencoded"
                    encoded_body = urlencode(body) if body else ""
                    async with self._session.post(
                        url,
                        data=encoded_body,
                        headers=headers,
                        timeout=self._timeout,
                    ) as resp:
                        if resp.status == 200:
                            return await self._parse_json(resp)

                        if resp.status == 401 and attempt == 0:
                            _LOGGER.debug(
                                "[MyENGIE] 401 la POST %s — invalidez token și reîncerc",
                                url,
                            )
                            self._invalidate_token()
                            if await self.async_ensure_authenticated():
                                continue
                            _LOGGER.warning("POST %s → 401 (re-auth eșuat)", url)
                            return None

                        _LOGGER.warning("POST %s → %s", url, resp.status)
                        return None
                else:
                    async with self._session.post(
                        url,
                        json=body,
                        headers=headers,
                        timeout=self._timeout,
                    ) as resp:
                        if resp.status == 200:
                            return await self._parse_json(resp)

                        if resp.status == 401 and attempt == 0:
                            _LOGGER.debug(
                                "[MyENGIE] 401 la POST %s — invalidez token și reîncerc",
                                url,
                            )
                            self._invalidate_token()
                            if await self.async_ensure_authenticated():
                                continue
                            _LOGGER.warning("POST %s → 401 (re-auth eșuat)", url)
                            return None

                        _LOGGER.warning("POST %s → %s", url, resp.status)
                        return None

            except Exception:
                _LOGGER.exception("Eroare POST %s", url)
                return None
        return None

    # ──────────────────────────────────────────
    # Endpoint-uri date — identice cu debug_myengie.py fetch_all()
    # ──────────────────────────────────────────

    async def async_get_user_profile(self) -> dict | None:
        """GET /v1/user/me → profilul utilizatorului.

        debug_myengie.py [1/12]: _get("v1/user/me", "user.me")
        """
        raw = await self._get(URL_USER_ME)
        if raw and isinstance(raw, dict):
            return raw.get("data", raw)
        return None

    async def async_get_consumption_places(self) -> dict | None:
        """GET /v1/placesofconsumption → locuri de consum.

        debug_myengie.py [2/12]: _get("v1/placesofconsumption", ...)
        Response: {data: {places_of_consumption: [...], roles: [...]}}
        """
        raw = await self._get(URL_CONSUMPTION_PLACES)
        if raw and isinstance(raw, dict):
            data = raw.get("data", raw)
            # Salvez PA din prima POC dacă disponibil
            if data and isinstance(data, dict):
                pocs = data.get("places_of_consumption", []) or []
                if pocs and isinstance(pocs, list) and len(pocs) > 0:
                    first_poc = pocs[0]
                    if isinstance(first_poc, dict):
                        self._crm_account = first_poc.get("pa") or first_poc.get("clientId")
            return data
        return None

    async def async_get_divisions(self, poc: str, pa: str) -> dict | None:
        """GET /v1/placesofconsumption/divisions/{poc}?pa={pa}

        debug_myengie.py [7b/12]: _get(f"v1/placesofconsumption/divisions/{cp_id}", params={"pa": pa})
        """
        url = f"{API_BASE}/v1/placesofconsumption/divisions/{poc}"
        raw = await self._get(url, params={"pa": pa})
        if raw and isinstance(raw, dict):
            return raw.get("data", raw)
        return None

    async def async_get_index_readings(
        self, poc: str, division: str, pa: str,
        installation_number: str = "", serie_contor: str = "",
    ) -> dict | None:
        """GET /v1/index/{poc}?division={div}&pa={pa}&installation_number=...&serie_contor=...

        debug_myengie.py [7c/12]: _get(f"v1/index/{cp_id}", params={division, pa, installation_number, serie_contor})
        """
        url = f"{API_BASE}/v1/index/{poc}"
        params: dict[str, str] = {"division": division, "pa": pa}
        if installation_number:
            params["installation_number"] = installation_number
        if serie_contor:
            params["serie_contor"] = serie_contor
        raw = await self._get(url, params=params)
        if raw and isinstance(raw, dict):
            return raw.get("data", raw)
        return None

    async def async_get_prognosis(
        self, poc: str, installation_number: str, pa: str
    ) -> dict | None:
        """GET /v1/index/prognosis/{poc}?installation_number={inst}&pa={pa}

        debug_myengie.py [7d/12]: _get(f"v1/index/prognosis/{cp_id}", params={"pa": pa, "installation_number": inst_nr})
        """
        url = f"{API_BASE}/v1/index/prognosis/{poc}"
        params: dict[str, str] = {"pa": pa}
        if installation_number:
            params["installation_number"] = installation_number
        raw = await self._get(url, params=params)
        if raw and isinstance(raw, dict):
            return raw.get("data", raw)
        return None

    async def async_get_consumption_graph(
        self, poc: str, pa: str, start_date: str, end_date: str
    ) -> dict | None:
        """GET /v1/index/consumption/{poc}?startDate={s}&endDate={e}&pa={pa}

        debug_myengie.py [7e/12]: _get(f"v1/index/consumption/{cp_id}", params={"startDate": ..., "endDate": ..., "pa": pa})
        """
        url = f"{API_BASE}/v1/index/consumption/{poc}"
        raw = await self._get(
            url,
            params={"startDate": start_date, "endDate": end_date, "pa": pa},
        )
        if raw and isinstance(raw, dict):
            return raw.get("data", raw)
        return None

    async def async_get_balance_details(self, contract_accounts: list[int]) -> dict | None:
        """POST /v1/invoices/ballance-details cu JSON body.

        debug_myengie.py [5/12]: _post("v1/invoices/ballance-details", json_body={"contract_account": [...]})
        """
        url = f"{API_BASE}/v1/invoices/ballance-details"
        raw = await self._post(url, body={"contract_account": contract_accounts})
        if raw and isinstance(raw, dict):
            return raw.get("data", raw)
        return None

    async def async_get_invoices_history(
        self, poc: str, pa: str, start_date: str = "", end_date: str = ""
    ) -> dict | None:
        """GET /v1/invoices/history/{poc}?pa={pa}&startDate=...&endDate=...

        debug_myengie.py [6/12]: _get(f"v1/invoices/history/{cp_id}", params={"pa": pa})
        """
        url = f"{API_BASE}/v1/invoices/history/{poc}"
        params: dict[str, str] = {"pa": pa}
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date
        raw = await self._get(url, params=params)
        if raw and isinstance(raw, dict):
            return raw.get("data", raw)
        return None

    async def async_get_payment_history(
        self, pa: str, start_date: str = "", end_date: str = ""
    ) -> dict | None:
        """GET /v1/invoices/payment/history/{pa}?startDate=...&endDate=...

        debug_myengie.py: _get(f"v1/invoices/payment/history/{clientId}", params={startDate, endDate})
        """
        url = f"{API_BASE}/v1/invoices/payment/history/{pa}"
        params: dict[str, str] = {}
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date
        raw = await self._get(url, params=params)
        if raw and isinstance(raw, dict):
            return raw.get("data", raw)
        return None

    async def async_get_simplified_inspection(
        self, poc: str, pod: str, pa: str
    ) -> dict | None:
        """GET /v1/widgets/newrv/{poc}/{pod}?pa={pa}

        debug_myengie.py [7g/12]: _get(f"v1/widgets/newrv/{cp_id}/{pod}", params={"pa": pa})
        Returnează: {last_verify_date, last_revision_date, next_inspection_date, ...}
        """
        url = f"{API_BASE}/v1/widgets/newrv/{poc}/{pod}"
        raw = await self._get(url, params={"pa": pa})
        if raw and isinstance(raw, dict):
            return raw.get("data", raw)
        return None

    async def async_get_technical_services_data(
        self, poc: str, pod: str, pa: str
    ) -> dict | None:
        """GET /v1/notifications/technical-services-data/{poc}/{pod}?pa={pa}

        debug_myengie.py [7g2/12]: _get(f"v1/notifications/technical-services-data/{cp_id}/{pod}", params={"pa": pa})
        """
        url = f"{API_BASE}/v1/notifications/technical-services-data/{poc}/{pod}"
        raw = await self._get(url, params={"pa": pa})
        if raw and isinstance(raw, dict):
            return raw.get("data", raw)
        return None

    async def async_get_green_bill_status(self, poc: str, pa: str) -> dict | None:
        """GET /v1/placesofconsumption/{poc}/greenbill/status?pa={pa}

        debug_myengie.py [7f/12]: _get(f"v1/placesofconsumption/{cp_id}/greenbill/status", params={"pa": pa})
        """
        url = f"{API_BASE}/v1/placesofconsumption/{poc}/greenbill/status"
        raw = await self._get(url, params={"pa": pa})
        if raw and isinstance(raw, dict):
            return raw.get("data", raw)
        return None

    async def async_get_distributors(self, poc: str) -> dict | None:
        """GET /v1/distributors/placesofconsumption/{poc}

        debug_myengie.py [7j/12]: _get(f"v1/distributors/placesofconsumption/{cp_id}")
        """
        url = f"{API_BASE}/v1/distributors/placesofconsumption/{poc}"
        raw = await self._get(url)
        if raw and isinstance(raw, dict):
            return raw.get("data", raw)
        return None

    async def async_get_notifications(self) -> dict | None:
        """GET /v1/notifications → notificări utilizator.

        debug_myengie.py [9/12]: _get("v1/notifications")
        """
        raw = await self._get(URL_NOTIFICATIONS)
        if raw and isinstance(raw, dict):
            return raw.get("data", raw)
        return None

    async def async_get_notifications_unread(self) -> dict | None:
        """GET /v1/notifications/unread-number → nr. notificări necitite.

        debug_myengie.py [9/12]: _get("v1/notifications/unread-number")
        """
        raw = await self._get(URL_NOTIFICATIONS_UNREAD)
        if raw and isinstance(raw, dict):
            return raw.get("data", raw)
        return None

    # ──────────────────────────────────────────
    # Acțiuni (POST)
    # ──────────────────────────────────────────

    async def async_get_index_history(
        self, poc_number: str, pa: str, division: str,
        installation_number: str = "", serie_contor: str = "",
        autocit: str = "", start_date: str = "",
    ) -> dict | None:
        """POST /v1/index/history cu JSON body → istoric citiri contor.

        Captură reală din browser (my.engie.ro):
            Content-Type: application/json
            Body: {"autocit":"3098793","poc_number":"5001464750","division":"gaz","start_date":"2023-04-01"}

        IMPORTANT:
          - Body e JSON (NU form-urlencoded)
          - Câmpul datei e "start_date" (snake_case), NU "startDate"
          - autocit trebuie să fie valoarea reală din index_readings (ex: "3098793")
          - pa, installation_number, serie_contor NU sunt trimise în request-ul web
        """
        url = f"{API_BASE}/v1/index/history"

        if not start_date:
            # APK exact: LocalDate.now().minusYears(3).plusDays(1)
            from datetime import datetime, timedelta
            now = datetime.now()
            try:
                three_years_ago = now.replace(year=now.year - 3)
            except ValueError:
                # 29 feb → 28 feb
                three_years_ago = now.replace(year=now.year - 3, day=28)
            start_date = (three_years_ago + timedelta(days=1)).strftime("%Y-%m-%d")

        body: dict[str, str] = {
            "autocit": autocit,
            "poc_number": poc_number,
            "division": division,
            "start_date": start_date,
        }

        raw = await self._post(url, body=body, form_data=False)
        if raw and isinstance(raw, dict):
            return raw.get("data", raw)
        if raw and isinstance(raw, list):
            return raw
        return None

    async def async_submit_self_reading(self, payload: dict) -> dict | None:
        """POST /v1/index cu form-urlencoded body → trimite autocitire.

        debug_myengie.py: _post("v1/index", body={poc_number, pa, installation_number, division, index, ...})
        Body type: form (urlencode), NU JSON.
        """
        url = f"{API_BASE}/v1/index"
        return await self._post(url, body=payload, form_data=True)

    async def async_get_contracts(self) -> list | None:
        """GET /v1/contracts → lista contracte per POC.

        Captură reală browser (my.engie.ro):
            GET https://gwss.engie.ro/myservices/v1/contracts
            Response: {data: [{pa, poc_number, contracts: [{from_date, to_date, status,
                        contract_number, division, installation_number, ...}], ...}]}
        """
        url = f"{API_BASE}/v1/contracts"
        raw = await self._get(url)
        if raw and isinstance(raw, dict):
            data = raw.get("data", raw)
            if isinstance(data, list):
                return data
            return [data] if data else []
        if raw and isinstance(raw, list):
            return raw
        return None

    async def async_get_partners(self, pa: str) -> list | None:
        """GET /v1/partner/details → lista titulari contract.

        Captură reală browser (my.engie.ro):
            GET https://gwss.engie.ro/myservices/v1/partner/details
            Response: {data: [{pa, lastName, firstName, cnp_cui, type,
                        partnerEmail, partnerMobile, addresses: [...], ...}]}
        """
        url = f"{API_BASE}/v1/partner/details"
        raw = await self._get(url)
        if raw and isinstance(raw, dict):
            data = raw.get("data", raw)
            if isinstance(data, list):
                return data
            return [data] if data else []
        if raw and isinstance(raw, list):
            return raw
        return None

    # ──────────────────────────────────────────
    # Token persistence (pentru restart HA)
    # ──────────────────────────────────────────

    def export_token_data(self) -> dict | None:
        """Exportă datele de token pentru persistare."""
        if not self._token:
            return None
        return {
            "token": self._token,
            "refresh_token": self._refresh_token,
            "id_token": self._id_token,
            "token_expires_in": self._token_expires_in,
            "crm_account": self._crm_account,
            "obtained_at_wall": time.time() - (time.monotonic() - self._token_obtained_at),
        }

    def inject_token(self, token_data: dict) -> None:
        """Restaurează un token salvat anterior."""
        self._token = token_data.get("token")
        self._refresh_token = token_data.get("refresh_token")
        self._id_token = token_data.get("id_token")
        self._token_expires_in = token_data.get("token_expires_in", TOKEN_MAX_AGE)
        self._crm_account = token_data.get("crm_account")

        wall = token_data.get("obtained_at_wall")
        if wall:
            age = max(0.0, time.time() - wall)
            self._token_obtained_at = time.monotonic() - age
        else:
            self._token_obtained_at = 0.0
