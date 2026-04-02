# Ghid de debugging — MyENGIE România

Acest ghid explică cum activezi logarea detaliată, ce mesaje să cauți, și cum interpretezi fiecare situație.

---

## 1. Activează debug logging

Editează `configuration.yaml` și adaugă:

```yaml
logger:
  default: warning
  logs:
    custom_components.myengie: debug
```

Restartează Home Assistant (**Setări** → **Sistem** → **Restart**).

Pentru a reduce zgomotul din loguri, poți adăuga:

```yaml
logger:
  default: warning
  logs:
    custom_components.myengie: debug
    homeassistant.const: critical
    homeassistant.loader: critical
    homeassistant.helpers.frame: critical
```

**Important**: dezactivează debug logging după ce ai rezolvat problema (setează `custom_components.myengie: info` sau șterge blocul). Logarea debug generează mult text și poate conține date personale.

---

## 2. Unde găsești logurile

### Din UI

**Setări** → **Sistem** → **Jurnale** → filtrează după `myengie`

### Din fișier

```bash
# Calea implicită
cat config/home-assistant.log | grep -i myengie

# Doar erorile
grep -E "(ERROR|WARNING).*myengie" config/home-assistant.log

# Ultimele 100 linii
grep -i myengie config/home-assistant.log | tail -100
```

### Din terminal (Docker/HAOS)

```bash
# Docker
docker logs homeassistant 2>&1 | grep -i myengie

# Home Assistant OS (SSH add-on)
ha core logs | grep -i myengie
```

---

## 3. Cum citești logurile API

Fiecare cerere API este etichetată cu `[MyENGIE]`. Formatul general:

```
[MyENGIE] mesaj descriptiv
Login MyENGIE reușit: email=..., token=..., exp=...
```

### Exemplu de ciclu normal de actualizare

```
[MyENGIE] Actualizare (refresh=#0, tip=HEAVY)
Login MyENGIE: POST https://gwss.engie.ro/myservices/v1/login (email=a******@exemplu.ro)
Login MyENGIE reușit: email=a******@exemplu.ro, token=eyJ..., exp=7200s
GET https://gwss.engie.ro/myservices/v1/user/me → 200
GET https://gwss.engie.ro/myservices/v1/contracts → 200
GET https://gwss.engie.ro/myservices/v1/partner/details → 200
GET https://gwss.engie.ro/myservices/v1/placesofconsumption → 200
GET https://gwss.engie.ro/myservices/v1/placesofconsumption/divisions/7002938475 → 200
GET https://gwss.engie.ro/myservices/v1/index/7002938475 → 200
POST https://gwss.engie.ro/myservices/v1/index/history → 200
GET https://gwss.engie.ro/myservices/v1/invoices/history/7002938475 → 200
GET https://gwss.engie.ro/myservices/v1/index/consumption/7002938475 → 200
GET https://gwss.engie.ro/myservices/v1/invoices/payment/history/192408571236 → 200
GET https://gwss.engie.ro/myservices/v1/widgets/newrv/7002938475/DGSIFILI0000123456 → 200
[MyENGIE] Fetch POC 7002938475 (PA 192408571236): gaz=1, elec=0, instalații=1, facturi=3, balanță=0.00, inspecții=1
[MyENGIE] Actualizare finalizată: 1 POC-uri, 1 instalații gaz+elec
[MyENGIE] Se creează 11 senzori pentru 1 POC-uri
```

### Endpoint-uri și senzori asociați

| Endpoint | Descriere | Senzor asociat |
|----------|-----------|----------------|
| `/v1/login` | Autentificare (form-urlencoded) | — (autentificare) |
| `/v1/user/me` | Profil utilizator | — (date interne) |
| `/v1/contracts` | Contracte | Date contract |
| `/v1/partner/details` | Date titular | Date utilizator |
| `/v1/placesofconsumption` | POC-uri (locuri de consum) | — (structură) |
| `/v1/placesofconsumption/divisions/{poc}` | Divizii gaz/elec | — (structură) |
| `/v1/index/{poc}` | Index readings | Index contor, Citire permisă |
| `/v1/index/history` | Istoric citiri (POST JSON) | Istoric citiri |
| `/v1/index/prognosis/{poc}` | Prognoză | — (intern) |
| `/v1/index/consumption/{poc}` | Grafic consum | Arhiva consum lunar |
| `/v1/invoices/history/{poc}` | Facturi | Arhivă facturi, Factură restantă |
| `/v1/invoices/payment/history/{pa}` | Plăți | Arhivă plăți |
| `/v1/invoices/ballance-details` | Sold (POST JSON) | Sold total |
| `/v1/widgets/newrv/{poc}/{pod}` | Revizie tehnică | Revizie tehnică |
| `/v1/index` | Trimitere autocitire (POST form) | Buton Trimite index |

---

## 4. Mesajele de la pornire

La prima pornire a integrării (sau după restart), ar trebui să vezi:

```
INFO  [MyENGIE] Se configurează integrarea myengie (entry_id=01ABC...).
DEBUG [MyENGIE] Interval actualizare: 3600s, heavy multiplier: 6.
DEBUG [MyENGIE] Actualizare (refresh=#0, tip=HEAVY)
DEBUG Login MyENGIE reușit: email=a******@exemplu.ro, token=eyJ..., exp=7200s
DEBUG [MyENGIE] Fetch POC 7002938475 (PA 192408571236): gaz=1, elec=0, ...
DEBUG [MyENGIE] Actualizare finalizată: 1 POC-uri, 1 instalații gaz+elec
INFO  [MyENGIE] Se creează 11 senzori pentru 1 POC-uri
INFO  [MyENGIE:Button] Se adaugă 1 butoane pentru 1 POC-uri
INFO  Integrarea myengie configurată (entry_id=01ABC...).
```

---

## 5. Situații normale (nu sunt erori)

### Token reutilizat

```
[MyENGIE] Token valid, nu se re-autentifică.
```

**Cauza**: token-ul JWT nu a expirat încă (~2h validitate). Comportament normal.

### Heavy refresh skip

```
[MyENGIE] Actualizare (refresh=#3, tip=light)
```

**Cauza**: plățile și green bill se actualizează doar la fiecare al 6-lea ciclu (heavy refresh). Ciclurile intermediare sunt „light". Comportament normal pentru a reduce încărcarea API.

### Licență — heartbeat

```
[LICENSE] Heartbeat OK. Licența este validă (expiră: 2027-01-15).
```

**Cauza**: verificarea periodică a licenței cu serverul a reușit. Comportament normal.

### POST index/history fără autocit

```
[MyENGIE] Eroare la index history gaz POC 7002938475 inst 4008261593: ...
```

**Cauza posibilă**: câmpul `autocit` nu a fost extras din `index_readings` (poate fi gol la prima instalare a contorului). Senzorul Istoric citiri va arăta 0 — nu e o eroare critică.

---

## 6. Situații de eroare

### Autentificare eșuată

```
Login eșuat: status=401, email=...
```

**Cauza**: email sau parolă incorectă.

**Rezolvare**:
1. Verifică credențialele pe [my.engie.ro](https://my.engie.ro/)
2. Reconfigurează integrarea cu credențiale corecte (Setări → Dispozitive și Servicii → MyENGIE România → Configurare)

### Server în mentenanță

```
[MyENGIE] Serverul Engie este în MENTENANȚĂ — răspuns HTML în loc de JSON
```

**Cauza**: serverul ENGIE returnează o pagină HTML de mentenanță în loc de JSON.

**Rezolvare**: Așteaptă. Integrarea reîncearcă automat la următorul ciclu.

### Eroare de rețea / timeout

```
[MyENGIE] Eroare GET https://gwss.engie.ro/...: TimeoutError
```

**Cauza**: API-ul ENGIE nu răspunde sau conexiunea HA la internet e întreruptă.

**Rezolvare**:
1. Verifică conexiunea la internet din HA
2. Integrarea reîncearcă automat la următorul ciclu
3. Dacă persistă, verifică dacă `https://gwss.engie.ro` este accesibil

### Eroare POST index/history (400 sau 500)

```
POST https://gwss.engie.ro/myservices/v1/index/history → 400
POST https://gwss.engie.ro/myservices/v1/index/history → 500
```

**Cauza**: parametrii trimiși nu sunt corecți (autocit lipsă, format greșit).

**Rezolvare**: Verifică logurile pentru valoarea `autocit` transmisă. Dacă e goală, index_readings nu conține câmpul `autocit` pentru acea instalație.

### Licență invalidă

```
[LICENSE] Licența nu este validă. Motiv: expired / invalid_key / server_unreachable.
[MyENGIE] Licență invalidă — se creează doar LicentaNecesaraSensor.
```

**Cauza**: licența a expirat, cheia este greșită, sau serverul de licențe nu este accesibil.

**Rezolvare**:
1. Verifică cheia de licență în OptionsFlow
2. Dacă a expirat, reînnoiește de la [hubinteligent.org/licenta/myengie](https://hubinteligent.org/licenta/myengie)
3. Dacă serverul nu e accesibil, există un grace period — licența rămâne validă temporar

---

## 7. Logare date API

La nivel debug, integrarea loghează statusul răspunsurilor HTTP:

```
GET https://gwss.engie.ro/myservices/v1/index/7002938475 → 200
POST https://gwss.engie.ro/myservices/v1/index/history → 200
POST https://gwss.engie.ro/myservices/v1/invoices/ballance-details → 200
```

**Atenție**: logurile debug conțin date personale (token-uri, coduri POC, adrese). **Nu le posta public fără a le anonimiza.**

---

## 8. Cum raportezi un bug

1. Activează debug logging (secțiunea 1)
2. Reproduce problema
3. Deschide un [issue pe GitHub](https://github.com/cnecrea/myengie/issues) cu:
   - **Descrierea problemei** — ce ai așteptat vs. ce s-a întâmplat
   - **Logurile relevante** — filtrează după `myengie` și include 20–50 linii relevante
   - **Versiunea HA** — din **Setări** → **Despre**
   - **Versiunea integrării** — din `manifest.json` sau HACS
   - **Diagnostics** — descarcă din Setări → Dispozitive și Servicii → MyENGIE România → Diagnostics

### Cum postezi loguri pe GitHub

Folosește blocuri de cod delimitate de 3 backticks:

````
```
2026-04-01 10:15:12 DEBUG custom_components.myengie [MyENGIE] Fetch POC 7002938475...
2026-04-01 10:15:13 WARNING custom_components.myengie POST .../v1/index/history → 500
```
````

Dacă logul e foarte lung (peste 50 linii), folosește secțiunea colapsabilă:

````
<details>
<summary>Log complet (click pentru a expanda)</summary>

```
... logul aici ...
```

</details>
````

> **Nu posta parola, token-ul sau date personale în loguri.** Integrarea loghează token-urile la login — anonimizează-le înainte de a le posta.
