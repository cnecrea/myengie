# MyENGIE România — Integrare Home Assistant

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.11%2B-41BDF5?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/cnecrea/myengie)](https://github.com/cnecrea/myengie/releases)
[![GitHub Stars](https://img.shields.io/github/stars/cnecrea/myengie?style=flat&logo=github)](https://github.com/cnecrea/myengie/stargazers)
[![Instalări](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/cnecrea/myengie/main/statistici/shields/descarcari.json)](https://github.com/cnecrea/myengie)
[![Ultima versiune](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/cnecrea/myengie/main/statistici/shields/ultima_release.json)](https://github.com/cnecrea/myengie/releases/latest)

Integrare custom pentru [Home Assistant](https://www.home-assistant.io/) care monitorizează datele contractuale, consumul și facturile prin API-ul [ENGIE Romania](https://my.engie.ro/) (platforma „MyENGIE").

Oferă senzori dedicați per POC (loc de consum) și per utilitate (gaz / electricitate): sold, facturi, plăți, citire permisă, index contor, istoric citiri, revizie tehnică gaz, date contract, date utilizator, și butoane de trimitere autocitiri. Suportă complet **multi-POC** (mai multe locuri de consum asociate aceluiași cont).

---

## Ce face integrarea

- **Descoperire automată** a locurilor de consum (POC) și a instalațiilor per utilitate
- **Multi-POC** — un singur config_entry extrage datele pentru TOATE POC-urile contului
- **Senzori per utilitate** — fiecare POC poate avea gaz, electricitate sau ambele; fiecare utilitate devine un device separat
- **Sold și facturi** — sold total (RON), facturi restante
- **Index contor** — index curent per contor (instalație), cu date ultima citire în atribute
- **Istoric citiri** — ultimele 12 citiri contoare (format identic MyElectrica), cu tip citire și dată
- **Arhive** — facturi și plăți pe anul curent, cu sume per intrare și totaluri
- **Date contract** — status contract (Activ), perioadă, nr. contract
- **Date utilizator** — titular contract (nume, email, telefon, adresă)
- **Revizie tehnică gaz** — Validă / Expirată / Nedefinit, cu date revizii și verificări
- **Trimitere autocitiri** — buton per contor care citește din `input_number` și trimite la API
- **Sistem de licență** — fără licență validă se afișează doar senzorul „Licență necesară"
- **Reconfigurare fără reinstalare** — OptionsFlow pentru credențiale și licență

---

## Sursa datelor

Datele vin prin API-ul backend ENGIE Romania la `https://gwss.engie.ro/myservices`, care expune endpoint-uri REST:

| Endpoint | Descriere |
|----------|-----------|
| `/v1/login` | Autentificare (form-urlencoded) — returnează JWT token |
| `/v1/user/me` | Profil utilizator |
| `/v1/placesofconsumption` | Locuri de consum (POC-uri) |
| `/v1/placesofconsumption/divisions/{poc}` | Divizii (gaz/elec) + detalii instalații |
| `/v1/index/{poc}` | Index readings per instalație |
| `/v1/index/history` | Istoric citiri contoare (POST JSON) |
| `/v1/index/prognosis/{poc}` | Prognoză consum |
| `/v1/index/consumption/{poc}` | Grafic consum lunar |
| `/v1/invoices/history/{poc}` | Facturi |
| `/v1/invoices/payment/history/{pa}` | Plăți |
| `/v1/invoices/ballance-details` | Sold total (POST JSON) |
| `/v1/contracts` | Contracte per POC |
| `/v1/partner/details` | Date titular contract |
| `/v1/widgets/newrv/{poc}/{pod}` | Revizie tehnică simplificată |
| `/v1/index` | Trimitere autocitire (POST form) |

Autentificarea se face cu email + parolă (POST form-urlencoded). Token-ul JWT are validitate ~2h. Re-autentificarea este automată.

---

## Instalare

### HACS (recomandat)

1. Deschide HACS în Home Assistant
2. Click pe cele 3 puncte din colțul dreapta sus → **Custom repositories**
3. Adaugă URL-ul: `https://github.com/cnecrea/myengie`
4. Categorie: **Integration**
5. Click **Add** → găsește „MyENGIE România" → **Install**
6. Restartează Home Assistant

### Manual

1. Copiază folderul `custom_components/myengie/` în directorul `config/custom_components/` din Home Assistant
2. Restartează Home Assistant

---

## Configurare

### Pasul 1 — Adaugă integrarea

1. **Setări** → **Dispozitive și Servicii** → **Adaugă Integrare**
2. Caută „**MyENGIE**" sau „**ENGIE**"
3. Completează formularul:

| Câmp | Descriere | Implicit |
|------|-----------|----------|
| **Email** | Adresa de email a contului MyENGIE | — |
| **Parolă** | Parola contului MyENGIE | — |
| **Interval actualizare** | Secunde între interogările API | `3600` (1 oră) |

### Pasul 2 — Licență

Integrarea necesită o licență validă. Poți achiziționa una de la [hubinteligent.org/donate?ref=myengie](https://hubinteligent.org/donate?ref=myengie). Licența se introduce din **OptionsFlow** (Setări → Dispozitive și Servicii → MyENGIE România → Configurare).

### Pasul 3 — Descoperire automată POC-uri

După autentificare, integrarea descoperă automat toate locurile de consum (POC) și utilitățile (gaz/electricitate) asociate contului. Fiecare POC generează device-uri separate per utilitate. Nu trebuie să selectezi manual — totul este automat.

Detalii complete în [SETUP.md](SETUP.md).

---

## Entități create

### Structura device-urilor

Integrarea creează un **device per POC per utilitate**. Exemple:
- `MyENGIE România (7002938475) Gaz`
- `MyENGIE România (7002938475) Energie Electrică`

### Pattern entity_id

Toate entitățile urmează pattern-ul: `{platformă}.myengie_{poc}_{utilitate}_{suffix}`

| `{utilitate}` | Utilitate API |
|---|---|
| `gaz` | gaz |
| `electricitate` | elec |

### Senzori per utilitate

| Senzor | Entity ID | Valoare principală | Icon |
|--------|-----------|-------------------|------|
| Sold total | `sensor.myengie_{poc}_{ut}_sold_total` | Sumă RON | mdi:cash |
| Citire permisă | `sensor.myengie_{poc}_{ut}_citire_permisa` | Da / Nu | mdi:clock-alert-outline |
| Arhivă facturi | `sensor.myengie_{poc}_{ut}_arhiva_facturi` | Nr facturi (anul curent) | mdi:file-document-multiple-outline |
| Arhivă plăți | `sensor.myengie_{poc}_{ut}_arhiva_plati` | Nr plăți (anul curent) | mdi:cash-check |
| Date contract | `sensor.myengie_{poc}_{ut}_date_contract` | Activ / Inactiv | mdi:file-sign |
| Date utilizator | `sensor.myengie_{poc}_{ut}_date_utilizator` | Nume titular | mdi:account-details |
| Arhiva consum lunar | `sensor.myengie_{poc}_{ut}_consum_grafic` | Total consum anul curent | mdi:chart-line |
| Factură restantă | `sensor.myengie_{poc}_{ut}_factura_restanta` | Da / Nu | mdi:file-document-alert |

### Senzori per contor (instalație)

| Senzor | Entity ID | Valoare principală | Icon |
|--------|-----------|-------------------|------|
| Index contor | `sensor.myengie_{poc}_{ut}_index_contor_{inst}` | Valoare index (m³ / kWh) | mdi:counter |
| Istoric citiri | `sensor.myengie_{poc}_{ut}_istoric_citiri_{inst}` | Nr citiri (max 12) | mdi:history |

### Senzori specifici gaz

| Senzor | Entity ID | Valoare principală | Icon |
|--------|-----------|-------------------|------|
| Revizie tehnică | `sensor.myengie_{poc}_gaz_revizie_tehnica` | Validă / Expirată / Nedefinit | mdi:wrench-clock |

### Senzor licență (fără licență validă)

| Senzor | Entity ID | Valoare principală | Icon |
|--------|-----------|-------------------|------|
| Licență necesară | `sensor.myengie_{poc}_licenta` | „Licență necesară" | mdi:license |

### Butoane

| Buton | Entity ID | Icon | Condiție |
|-------|-----------|------|----------|
| Trimite index | `button.myengie_{poc}_{ut}_trimite_index` | mdi:fire (gaz) / mdi:flash (electricitate) | Licență validă |

---

## Atribute detaliate per senzor

### Citire permisă

Atribute:
```yaml
Început perioadă: "24 aprilie 2026"
Sfârșit perioadă: "28 aprilie 2026"
attribution: Date furnizate de ENGIE Romania
```

### Istoric citiri

Atribute (format identic MyElectrica):
```yaml
Index (estimat) 24 martie 2026: "8197"
Index (citit distribuitor) 25 februarie 2026: "8196"
Index (estimat) 24 ianuarie 2026: "7957"
Serie contor: "22031238007"
Total citiri: "12"
attribution: Date furnizate de ENGIE Romania
```

### Arhivă facturi

Atribute:
```yaml
Emisă pe 4 martie 2026: "125,50 lei"
Emisă pe 15 februarie 2026: "98,20 lei"
Total facturi: "2"
Total facturat: "223,70 lei"
```

### Arhivă plăți

Atribute:
```yaml
Plată pe 10 martie 2026: "125,50 lei (Ordin de plată)"
Total plăți: "1"
Total plătit: "125,50 lei"
attribution: Date furnizate de ENGIE Romania
```

### Date contract

Atribute:
```yaml
Nr. contract: "3018294756"
Descriere: "contract furnizare"
Început contract: "1 aprilie 2026"
Sfârșit contract: "31 octombrie 2026"
Status: "Activ"
Nr. cont contract: "2109537864"
Nr. instalație: "4008261593"
Division: "gaz"
Document disponibil: "Da"
attribution: Date furnizate de ENGIE Romania
```

### Date utilizator

Atribute:
```yaml
Nume: "Marinescu"
Prenume: "Alexandru Andrei"
Tip cont: "Persoană fizică"
Email: "alexandru.marinescu@exemplu.ro"
Telefon mobil: "0745123456"
Telefon fix: "N/A"
PA: "192408571236"
Adresă: "Strada Primăverii, Nr. 15, București, Sector 1"
attribution: Date furnizate de ENGIE Romania
```

### Factură restantă

Atribute:
```yaml
Total restantă: "223.70 RON"
Sold total: "223.70 RON"
Facturi neachitate: 2
```

### Revizie tehnică gaz

Atribute:
```yaml
Data ultimei revizii: "15 iunie 2024"
Data ultimei verificări: "10 septembrie 2023"
Data următoarei inspecții: "15 iunie 2026"
Tipul următoarei inspecții: "Verificare"
Depășită: "Nu"
```

---

## Exemple de automatizări

### Notificare factură restantă

```yaml
automation:
  - alias: "Notificare factură restantă ENGIE"
    trigger:
      - platform: state
        entity_id: sensor.myengie_7002938475_gaz_factura_restanta
        to: "Da"
    action:
      - service: notify.mobile_app_telefonul_meu
        data:
          title: "Factură restantă ENGIE"
          message: >
            Ai {{ state_attr('sensor.myengie_7002938475_gaz_factura_restanta', 'Total restantă') }}
            de plătit.
```

### Card pentru Dashboard

```yaml
type: entities
title: MyENGIE România - Gaz
entities:
  - entity: sensor.myengie_7002938475_gaz_date_contract
    name: Contract
  - entity: sensor.myengie_7002938475_gaz_sold_total
    name: Sold total
  - entity: sensor.myengie_7002938475_gaz_citire_permisa
    name: Citire permisă
  - entity: sensor.myengie_7002938475_gaz_factura_restanta
    name: Factură restantă
  - entity: sensor.myengie_7002938475_gaz_revizie_tehnica
    name: Revizie tehnică
```

### Card condiționat — Alertă factură restantă

```yaml
type: conditional
conditions:
  - condition: state
    entity: sensor.myengie_7002938475_gaz_factura_restanta
    state: "Da"
card:
  type: markdown
  content: >-
    ## Ai factură restantă ENGIE!

    **Total restantă:** {{ state_attr('sensor.myengie_7002938475_gaz_factura_restanta', 'Total restantă') }}

    Verifică detaliile în secțiunea Facturi.
```

---

## Structura fișierelor

```
custom_components/myengie/
├── __init__.py          # Setup/unload integrare (runtime_data, licență, heartbeat)
├── api.py               # MyEngieApiClient — login, GET/POST, token management
├── button.py            # Butoane trimitere autocitiri per contor (gaz / electricitate)
├── config_flow.py       # ConfigFlow + OptionsFlow (autentificare, licență)
├── const.py             # Constante, URL-uri API (gwss.engie.ro)
├── coordinator.py       # DataUpdateCoordinator — multi-POC fetch paralel
├── diagnostics.py       # Diagnostics pentru troubleshooting
├── helpers.py           # Funcții utilitare
├── license.py           # Manager licență (server-side v3.3, Ed25519, HMAC-SHA256)
├── manifest.json        # Metadata integrare
├── sensor.py            # 12 clase senzor + LicentaNecesaraSensor
├── strings.json         # Traduceri implicite (engleză)
└── translations/
    ├── en.json          # Traduceri engleză
    └── ro.json          # Traduceri române
```

---

## Cerințe

- **Home Assistant** 2025.11 sau mai nou (pattern `entry.runtime_data`)
- **HACS** (opțional, pentru instalare ușoară)
- **Cont MyENGIE** activ cu email + parolă — [my.engie.ro](https://my.engie.ro/)
- **Licență** validă — [hubinteligent.org/donate?ref=myengie](https://hubinteligent.org/donate?ref=myengie)
- **Python**: `cryptography >= 41.0.0` (dependință automată prin manifest)

---

## Limitări cunoscute

1. **O singură instanță per cont** — dacă încerci să adaugi același email de două ori, vei primi eroare.

2. **Citire permisă** — se bazează pe intervalul de autocitire (`next_read_dates`) raportat de API. „Da" doar dacă data curentă este în intervalul `[startDate, endDate]`.

3. **Trimitere autocitiri** — butonul citește din `input_number.myengie_{poc}_{div}_{installation}_index`. Entitatea trebuie creată manual în `configuration.yaml`.

4. **Heavy refresh** — plățile și green bill se reîmprospătează doar la fiecare al 6-lea ciclu de actualizare (≈6h la interval implicit de 1h).

5. **Istoric citiri** — afișează ultimele 12 citiri. Datele vin din `POST /v1/index/history` (necesită `autocit` valid din `index_readings`).

---

## Susține dezvoltatorul

Dacă ți-a plăcut această integrare și vrei să sprijini munca depusă, **invită-mă la o cafea**!

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-Susține%20dezvoltatorul-orange?style=for-the-badge&logo=buy-me-a-coffee)](https://buymeacoffee.com/cnecrea)

---

## Contribuții

Contribuțiile sunt binevenite! Simte-te liber să trimiți un pull request sau să raportezi probleme [aici](https://github.com/cnecrea/myengie/issues).

---

## Suport
Dacă îți place această integrare, oferă-i un star pe [GitHub](https://github.com/cnecrea/myengie/)!


## Licență

[MIT](LICENSE)
