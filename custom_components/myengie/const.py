"""Constante pentru integrarea MyENGIE România (Engie Romania)."""

from homeassistant.const import Platform

DOMAIN = "myengie"

# ──────────────────────────────────────────────
# Configurare
# ──────────────────────────────────────────────
DEFAULT_UPDATE_INTERVAL = 3600      # 1 oră (secunde)
HEAVY_UPDATE_MULTIPLIER = 6         # Heavy refresh la fiecare al 6-lea ciclu (≈6h)

# ──────────────────────────────────────────────
# Licență
# ──────────────────────────────────────────────
CONF_LICENSE_KEY = "license_key"
LICENSE_DATA_KEY = "myengie_license_manager"
LICENSE_PURCHASE_URL = "https://hubinteligent.org/donate?ref=myengie"

# ──────────────────────────────────────────────
# Token store (între config_flow și __init__)
# ──────────────────────────────────────────────
DOMAIN_TOKEN_STORE = f"{DOMAIN}_token_store"

# ──────────────────────────────────────────────
# Token management
# ──────────────────────────────────────────────
TOKEN_REFRESH_THRESHOLD = 300       # Refresh cu 5 min înainte de expirare
TOKEN_MAX_AGE = 7200                # Token Engie expiră la 2 ore (din exp din răspuns)

# ──────────────────────────────────────────────
# Timeout API (secunde)
# ──────────────────────────────────────────────
API_TIMEOUT = 30

# ──────────────────────────────────────────────
# URL-uri API — MyENGIE România (Engie Romania)
# ──────────────────────────────────────────────
API_BASE = "https://gwss.engie.ro/myservices"
SAP_BASE = "https://gwss.engie.ro/sapservices/v2"

# Auth (OAuth2 / Auth0) — din BuildConfig.java APK decompilat
OAUTH_DOMAIN = "https://auth.engie.ro"
OAUTH_CLIENT_ID = "hMpDTLmC0C8szydob7zqUs231mQoDuyK"
OAUTH_AUDIENCE = "https://myservices.engie.ro"
URL_OAUTH_TOKEN = f"{OAUTH_DOMAIN}/oauth/token"

# Login
URL_LOGIN = f"{API_BASE}/v1/login"

# User profile
URL_USER_ME = f"{API_BASE}/v1/user/me"

# Consumption places
URL_CONSUMPTION_PLACES = f"{API_BASE}/v1/placesofconsumption"
# Divisions: f"{API_BASE}/v1/placesofconsumption/divisions/{poc}?pa={clientId}"
# Contracts: f"{API_BASE}/v1/placesofconsumption/contracts?pa={clientId}"
# Green bill: f"{API_BASE}/v1/placesofconsumption/{poc}/greenbill/status?pa={clientId}"
# Partners: f"{API_BASE}/v1/placesofconsumption/partners?pa={clientId}"

# Index (citiri contoare)
# GET v1/index/{poc}?division={div}&pa={clientId}&installation_number={inst}&serie_contor={serie}
# POST v1/index  — trimitere autocitire
# Prognosis: f"{API_BASE}/v1/index/prognosis/{poc}?installation_number={inst}&pa={clientId}"
# Consumption graph: f"{API_BASE}/v1/index/consumption/{poc}?startDate={s}&endDate={e}&pa={clientId}"

# Invoices
# POST v1/invoices/ballance-details  — body: {contract_account: [...]}
# GET v1/invoices/history/{poc}?pa={clientId}&startDate={s}&endDate={e}

# Payments
# GET v1/invoices/payment/history/{clientId}?startDate={s}&endDate={e}

# Notifications
URL_NOTIFICATIONS = f"{API_BASE}/v1/notifications"
URL_NOTIFICATIONS_UNREAD = f"{API_BASE}/v1/notifications/unread-number"

# Technical services
# Simplified inspection: f"{API_BASE}/v1/widgets/newrv/{poc}/{pod}?pa={clientId}"
# Tech services data: f"{API_BASE}/v1/notifications/technical-services-data/{poc}/{pod}?pa={clientId}"

# Distributors
# f"{API_BASE}/v1/distributors/placesofconsumption/{poc}"

# Saving tips
# f"{API_BASE}/v1/savingtips?poc_number={poc}&installation_number={inst}&division={div}"

# Cards
URL_CARDS = f"{API_BASE}/v1/cards"

# Call center
URL_CALL_CENTER = f"{API_BASE}/v1/callcenter"

# ──────────────────────────────────────────────
# Headers HTTP — MyENGIE Device Info (din APK decompilat)
# Cheile EXACTE din DeviceInfoProvider.java
# ──────────────────────────────────────────────
HEADERS_BASE = {
    "Accept": "application/json",
}

APP_VERSION = "2.1.11"
APP_VERSION_CODE = "177"
APP_ID = "ro.engie.agentia"

DEVICE_HEADERS = {
    "source": "android",
    "App-Version": APP_VERSION,
    "App-Build": APP_VERSION_CODE,
    "OS-Version": "14",
    "OS-Platform": "android",
    "Device-Type": "phone",
    "Device-Manufacturer": "Samsung",
    "Device-Model": "SM-S926B",
    "Screen-Height": "2340",
    "Screen-Width": "1080",
    "Device-Id": "ha-integration",
    "User-Agent": f"MyEngie/{APP_VERSION} (Android; {APP_ID}; build {APP_VERSION_CODE})",
}

# ──────────────────────────────────────────────
# Platforme suportate
# ──────────────────────────────────────────────
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON]

# ──────────────────────────────────────────────
# Atribuție
# ──────────────────────────────────────────────
ATTRIBUTION = "Date furnizate de ENGIE Romania"

# ──────────────────────────────────────────────
# Luni (pentru convenție consum / prognoza)
# ──────────────────────────────────────────────
MONTHS_EN = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]
MONTHS_RO = [
    "Ianuarie", "Februarie", "Martie", "Aprilie", "Mai", "Iunie",
    "Iulie", "August", "Septembrie", "Octombrie", "Noiembrie", "Decembrie",
]
