# Ghid de instalare și configurare — MyENGIE România

Acest ghid acoperă fiecare pas al instalării și configurării integrării MyENGIE România pentru Home Assistant. Dacă ceva nu e clar, deschide un [issue pe GitHub](https://github.com/cnecrea/myengie/issues).

---

## Cerințe preliminare

Înainte de a începe, asigură-te că ai:

- **Home Assistant** versiunea 2025.11 sau mai nouă (necesită pattern `entry.runtime_data`)
- **Cont MyENGIE** activ — cu email și parolă funcționale pe platforma [my.engie.ro](https://my.engie.ro/)
- **Licență** validă — de la [hubinteligent.org/donate?ref=myengie](https://hubinteligent.org/donate?ref=myengie)
- **HACS** instalat (opțional, dar recomandat) — [instrucțiuni HACS](https://hacs.xyz/docs/setup/download)

---

## Metoda 1: Instalare prin HACS (recomandat)

### Pasul 1 — Adaugă repository-ul custom

1. Deschide Home Assistant → sidebar → **HACS**
2. Click pe cele 3 puncte din colțul dreapta sus
3. Selectează **Custom repositories**
4. În câmpul „Repository" scrie: `https://github.com/cnecrea/myengie`
5. În câmpul „Category" selectează: **Integration**
6. Click **Add**

### Pasul 2 — Instalează integrarea

1. În HACS, caută „**MyENGIE România**" sau „**ENGIE**"
2. Click pe rezultat → **Download** (sau **Install**)
3. Confirmă instalarea

### Pasul 3 — Restartează Home Assistant

1. **Setări** → **Sistem** → **Restart**
2. Sau din terminal: `ha core restart`

**Așteptare**: restartul durează 1–3 minute. Nu continua până nu se încarcă complet dashboard-ul.

---

## Metoda 2: Instalare manuală

### Pasul 1 — Descarcă fișierele

1. Mergi la [Releases](https://github.com/cnecrea/myengie/releases) pe GitHub
2. Descarcă ultima versiune (zip sau tar.gz)
3. Dezarhivează

### Pasul 2 — Copiază folderul

Copiază întregul folder `custom_components/myengie/` în directorul de configurare al Home Assistant:

```
config/
└── custom_components/
    └── myengie/
        ├── __init__.py
        ├── api.py
        ├── button.py
        ├── config_flow.py
        ├── const.py
        ├── coordinator.py
        ├── diagnostics.py
        ├── helpers.py
        ├── license.py
        ├── manifest.json
        ├── sensor.py
        ├── strings.json
        └── translations/
            ├── en.json
            └── ro.json
```

**Atenție**: folderul trebuie să fie exact `myengie` (litere mici, fără spații).

Dacă folderul `custom_components` nu există, creează-l.

### Pasul 3 — Restartează Home Assistant

La fel ca la Metoda 1.

---

## Configurare inițială

### Pasul 1 — Adaugă integrarea

1. **Setări** → **Dispozitive și Servicii**
2. Click **+ Adaugă Integrare** (butonul albastru, dreapta jos)
3. Caută „**MyENGIE**" — va apărea „MyENGIE România"
4. Click pe ea

### Pasul 2 — Completează formularul de autentificare

Vei vedea un formular cu 3 câmpuri:

#### Câmp 1: Adresă de email

- **Ce face**: adresa de email a contului MyENGIE
- **Format**: email valid (ex: `utilizator@exemplu.ro`)
- **Observație**: este și identificatorul unic al integrării — nu poți adăuga același email de două ori

#### Câmp 2: Parolă

- **Ce face**: parola contului MyENGIE
- **Observație**: stocată criptat în baza de date HA

#### Câmp 3: Interval actualizare (secunde)

- **Ce face**: la câte secunde se reîmprospătează datele de la API
- **Implicit**: `3600` (1 oră)
- **Recomandare**: lasă pe 3600. Datele ENGIE nu se schimbă frecvent. Nu se recomandă valori sub 600 secunde.

### Pasul 3 — Descoperire automată POC-uri

După autentificare reușită, integrarea descoperă automat **toate locurile de consum (POC)** și utilitățile lor (gaz/electricitate).

Integrarea extrage datele pentru fiecare POC separat, în paralel. Fiecare POC și utilitate generează un device cu senzori proprii.

**Observație**: Nu trebuie să selectezi manual POC-urile — descoperirea este complet automată.

### Pasul 4 — Licență

Integrarea necesită o **licență validă** pentru a funcționa. Fără licență:
- Se creează doar senzorul `sensor.myengie_{poc}_licenta` cu valoarea „Licență necesară"
- Toți senzorii normali și butoanele sunt dezactivate

Pentru a introduce licența:
1. **Setări** → **Dispozitive și Servicii**
2. Găsește **MyENGIE România** → click pe **Configurare**
3. Selectează **Licență**
4. Introdu cheia de licență
5. Click **Salvează**

Licențe disponibile la: [hubinteligent.org/donate?ref=myengie](https://hubinteligent.org/donate?ref=myengie)

### Pasul 5 — Confirmă

Click **Salvează**. Integrarea se instalează și creează:
- 1 device per POC per utilitate (ex: „MyENGIE România (7002938475) Gaz")
- Senzori dedicați per device (sold, facturi, contract, index, istoric citiri, etc.)
- 1 buton de trimitere autocitiri per contor

Prima actualizare durează câteva secunde (interogare API pentru toate endpoint-urile per POC, în paralel).

---

## Reconfigurare (fără reinstalare)

Setările pot fi modificate din UI, fără a șterge și readăuga integrarea.

1. **Setări** → **Dispozitive și Servicii**
2. Găsește **MyENGIE România** → click pe **Configurare**
3. Poți modifica:
   - Credențialele (email, parolă)
   - Intervalul de actualizare
   - Cheia de licență
4. Click **Salvează**
5. Integrarea se reîncarcă automat (nu e nevoie de restart)

**Validare**: dacă modifici credențialele și noile date sunt greșite, vei primi o eroare și configurația existentă rămâne neschimbată.

---

## Referință rapidă — Entity ID-uri

### Senzori per utilitate (gaz / electricitate)

| Senzor | Entity ID |
|---|---|
| Sold total | `sensor.myengie_{poc}_{ut}_sold_total` |
| Citire permisă | `sensor.myengie_{poc}_{ut}_citire_permisa` |
| Arhivă facturi | `sensor.myengie_{poc}_{ut}_arhiva_facturi` |
| Arhivă plăți | `sensor.myengie_{poc}_{ut}_arhiva_plati` |
| Date contract | `sensor.myengie_{poc}_{ut}_date_contract` |
| Date utilizator | `sensor.myengie_{poc}_{ut}_date_utilizator` |
| Arhiva consum lunar | `sensor.myengie_{poc}_{ut}_consum_grafic` |
| Factură restantă | `sensor.myengie_{poc}_{ut}_factura_restanta` |

### Senzori per contor (instalație)

| Senzor | Entity ID |
|---|---|
| Index contor | `sensor.myengie_{poc}_{ut}_index_contor_{inst}` |
| Istoric citiri | `sensor.myengie_{poc}_{ut}_istoric_citiri_{inst}` |

### Senzori specifici gaz

| Senzor | Entity ID |
|---|---|
| Revizie tehnică | `sensor.myengie_{poc}_gaz_revizie_tehnica` |

### Butoane

| Buton | Entity ID |
|---|---|
| Trimite index | `button.myengie_{poc}_{ut}_trimite_index` |

**Unde**: `{poc}` = codul POC (ex: `7002938475`), `{ut}` = `gaz` sau `electricitate`, `{inst}` = nr. instalație (ex: `4008261593`).

---

## Pregătire pentru butoanele Trimite index

Butoanele de trimitere autocitiri citesc valoarea din entitatea `input_number` corespunzătoare.

Adaugă în `configuration.yaml`:

```yaml
input_number:
  myengie_7002938475_gaz_4008261593_index:
    name: Index contor gaz ENGIE
    min: 0
    max: 999999
    step: 1
    mode: box
```

> **Observație:** Înlocuiește `7002938475` și `4008261593` cu valorile reale ale POC-ului și nr. instalației tale. Le găsești în atributele senzorului de index sau în logurile de debug.

Restartează HA după adăugare.

---

## Exemple de carduri Lovelace

### Card general — toate entitățile

```yaml
type: entities
title: MyENGIE România - Gaz
entities:
  - entity: sensor.myengie_7002938475_gaz_date_contract
    name: Date contract
  - entity: sensor.myengie_7002938475_gaz_sold_total
    name: Sold total
  - entity: sensor.myengie_7002938475_gaz_citire_permisa
    name: Citire permisă
  - entity: sensor.myengie_7002938475_gaz_consum_grafic
    name: Consum anul curent
  - entity: sensor.myengie_7002938475_gaz_factura_restanta
    name: Factură restantă
  - entity: sensor.myengie_7002938475_gaz_revizie_tehnica
    name: Revizie tehnică
  - entity: button.myengie_7002938475_gaz_trimite_index
    name: Trimite index gaz
```

### Card — Istoric citiri contor

```yaml
type: entities
title: Istoric citiri gaz
entities:
  - entity: sensor.myengie_7002938475_gaz_istoric_citiri_4008261593
    name: Istoric citiri
  - type: attribute
    entity: sensor.myengie_7002938475_gaz_istoric_citiri_4008261593
    attribute: Serie contor
    name: Serie contor
  - type: attribute
    entity: sensor.myengie_7002938475_gaz_istoric_citiri_4008261593
    attribute: Total citiri
    name: Total citiri
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

    Verifică detaliile în secțiunea Facturi din dashboard.
```

---

## Verificare după instalare

### Verifică că device-urile există

1. **Setări** → **Dispozitive și Servicii** → click pe **MyENGIE România**
2. Ar trebui să vezi un device per POC per utilitate (ex: „MyENGIE România (7002938475) Gaz")

### Verifică senzorii

1. **Instrumente dezvoltator** → **Stări**
2. Filtrează după `myengie`
3. Ar trebui să vezi entitățile cu valori (ex: `Da`, `Nu`, `Activ`, `Validă`, sume RON, etc.)

### Verifică logurile (dacă ceva nu merge)

1. **Setări** → **Sistem** → **Jurnale**
2. Caută mesaje cu `myengie`
3. Pentru detalii, activează debug logging — vezi [DEBUG.md](DEBUG.md)

---

## Dezinstalare

### Prin HACS

1. HACS → găsește „MyENGIE România" → **Remove**
2. Restartează Home Assistant

### Manual

1. **Setări** → **Dispozitive și Servicii** → MyENGIE România → **Șterge**
2. Șterge folderul `config/custom_components/myengie/`
3. Restartează Home Assistant

---

## Observații generale

- **Înlocuiește `7002938475`** cu codul tău POC real în toate exemplele de mai sus.
- **Entity ID-urile sunt setate manual** de integrare pe baza codului POC, utilitații și (pentru contor) a nr. instalației.
- **Atributele apar doar când ENGIE furnizează datele.** Dacă un atribut nu e vizibil, înseamnă că API-ul nu a returnat acea informație — nu e o eroare.
- **Revizia tehnică gaz** afișează „Validă", „Expirată" sau „Nedefinit" — nu data brută.
- **Heavy refresh**: plățile se actualizează doar la fiecare al 6-lea ciclu (≈6h la interval implicit de 1h) pentru a reduce încărcarea API.
- Dacă întâmpini probleme, consultă [DEBUG.md](DEBUG.md) pentru activarea logării detaliate.
