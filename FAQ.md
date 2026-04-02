<a name="top"></a>
# Întrebări frecvente

- [Cum adaug integrarea în Home Assistant?](#cum-adaug-integrarea-în-home-assistant)
- [Am mai multe locuri de consum (POC). Sunt descoperite automat?](#am-mai-multe-locuri-de-consum-poc-sunt-descoperite-automat)
- [Ce senzori primesc per loc de consum?](#ce-senzori-primesc-per-loc-de-consum)
- [Ce înseamnă „Sold total"?](#ce-înseamnă-sold-total)
- [Ce înseamnă senzorul „Citire permisă"?](#ce-înseamnă-senzorul-citire-permisă)
- [Ce înseamnă senzorul „Istoric citiri"?](#ce-înseamnă-senzorul-istoric-citiri)
- [Nu îmi apare indexul curent. De ce?](#nu-îmi-apare-indexul-curent-de-ce)
- [Ce înseamnă senzorul „Factură restantă"?](#ce-înseamnă-senzorul-factură-restantă)
- [Ce înseamnă senzorul „Revizie tehnică"?](#ce-înseamnă-senzorul-revizie-tehnică)
- [De ce entitățile au un nume lung, cu codul POC inclus?](#de-ce-entitățile-au-un-nume-lung-cu-codul-poc-inclus)
- [Vreau să trimit indexul automat. De ce am nevoie?](#vreau-să-trimit-indexul-automat-de-ce-am-nevoie)
- [Ce e licența și de ce am nevoie de ea?](#ce-e-licența-și-de-ce-am-nevoie-de-ea)
- [Am introdus licența dar senzorii tot arată „Licență necesară". De ce?](#am-introdus-licența-dar-senzorii-tot-arată-licență-necesară-de-ce)
- [Am schimbat opțiunile integrării. Trebuie să restartez?](#am-schimbat-opțiunile-integrării-trebuie-să-restartez)
- [Trebuie să șterg și readaug integrarea la actualizare?](#trebuie-să-șterg-și-readaug-integrarea-la-actualizare)
- [Îmi place proiectul. Cum pot să-l susțin?](#îmi-place-proiectul-cum-pot-să-l-susțin)

---

## Cum adaug integrarea în Home Assistant?

[Înapoi la cuprins](#top)

Ai nevoie de HACS (Home Assistant Community Store) instalat. Dacă nu-l ai, urmează [ghidul oficial HACS](https://hacs.xyz/docs/use).

1. În Home Assistant, mergi la **HACS** → cele **trei puncte** din dreapta sus → **Custom repositories**.
2. Introdu URL-ul: `https://github.com/cnecrea/myengie` și selectează tipul **Integration**.
3. Apasă **Add**, apoi caută **MyENGIE România** în HACS și instalează.
4. Repornește Home Assistant.
5. Mergi la **Setări** → **Dispozitive și Servicii** → **Adaugă Integrare** → caută **MyENGIE** și urmează pașii de configurare.

Detalii complete în [SETUP.md](./SETUP.md).

---

## Am mai multe locuri de consum (POC). Sunt descoperite automat?

[Înapoi la cuprins](#top)

Da. Integrarea folosește endpoint-ul `/v1/placesofconsumption` care returnează lista completă de POC-uri (locuri de consum) asociate contului tău. La fiecare ciclu de actualizare, coordinator-ul extrage datele pentru fiecare POC în paralel.

Toate POC-urile descoperite generează device-uri și senzori proprii, fără intervenție manuală. De exemplu, dacă ai un POC cu gaz și altul cu electricitate, vei avea 2 device-uri:
- MyENGIE România (7002938475) Gaz
- MyENGIE România (7003847261) Energie Electrică

---

## Ce senzori primesc per loc de consum?

[Înapoi la cuprins](#top)

Pentru fiecare POC și fiecare utilitate (gaz / electricitate), se creează:

**Senzori per utilitate** (sub fiecare device): Sold total, Citire permisă, Arhivă facturi, Arhivă plăți, Date contract, Date utilizator, Arhiva consum lunar, Factură restantă.

**Senzori per contor** (per instalație): Index contor, Istoric citiri (ultimele 12 citiri).

**Senzori condiționali**: Revizie tehnică — apare doar pentru utilitatea gaz.

**Buton**: Trimite index — un buton per contor, trimite autocitirea la API.

---

## Ce înseamnă „Sold total"?

[Înapoi la cuprins](#top)

Senzorul „Sold total" (`sensor.myengie_{poc}_{ut}_sold_total`) afișează suma în RON pe care o ai de plătit sau credit pe care îl ai. Valoarea vine de la endpoint-ul `/v1/invoices/ballance-details`.

Este un senzor cu device_class `monetary` și state_class `total`, deci poate fi folosit în statistici și grafice HA.

---

## Ce înseamnă senzorul „Citire permisă"?

[Înapoi la cuprins](#top)

Senzorul „Citire permisă" (`sensor.myengie_{poc}_{ut}_citire_permisa`) indică dacă ești în perioada de autocitire:

- **Da** — data curentă este în intervalul de autocitire (`startDate` - `endDate` din `next_read_dates`)
- **Nu** — nu ești în perioada de autocitire (chiar dacă API-ul indică `permite_index = true`)

Atributele arată exact începutul și sfârșitul perioadei, formatate în română (ex: „24 aprilie 2026").

---

## Ce înseamnă senzorul „Istoric citiri"?

[Înapoi la cuprins](#top)

Senzorul „Istoric citiri" (`sensor.myengie_{poc}_{ut}_istoric_citiri_{inst}`) afișează ultimele 12 citiri ale contorului. Valoarea principală este numărul de citiri disponibile.

Atributele arată fiecare citire în formatul: `Index (tip) DATA: valoare`. Tipurile de citire sunt: „estimat" (estimare convenție consum), „citit distribuitor" (citire fizică), „autocitit" (autocitire din aplicație).

Datele vin din `POST /v1/index/history` — un endpoint care necesită câmpul `autocit` valid din `index_readings`.

---

## Nu îmi apare indexul curent. De ce?

[Înapoi la cuprins](#top)

Indexul curent vine de la endpoint-ul `/v1/index/{poc}` și depinde de ce returnează API-ul ENGIE. Dacă senzorul afișează `None` sau nu are valoare:

1. Verifică atributele senzorului Index contor — ar trebui să vezi POD, Nr. instalație, Autocitire
2. Dacă atributele sunt goale, API-ul ENGIE nu furnizează date de contor pentru acea instalație
3. Activează debug logging ([DEBUG.md](DEBUG.md)) și verifică răspunsul endpoint-ului `index`

Dacă ești client nou sau contorul nu a fost citit niciodată, e posibil ca API-ul să nu aibă date.

---

## Ce înseamnă senzorul „Factură restantă"?

[Înapoi la cuprins](#top)

Senzorul „Factură restantă" (`sensor.myengie_{poc}_{ut}_factura_restanta`) indică dacă ai facturi neachitate:

- **Da** — ai facturi cu câmpul `unpaid` diferit de 0
- **Nu** — toate facturile sunt achitate

Atribute disponibile: Total restantă (RON), Sold total (RON), Facturi neachitate (nr).

---

## Ce înseamnă senzorul „Revizie tehnică"?

[Înapoi la cuprins](#top)

Senzorul „Revizie tehnică" (`sensor.myengie_{poc}_gaz_revizie_tehnica`) apare doar pentru utilitatea gaz și arată starea reviziei tehnice a instalației:

- **Validă** — revizia nu a expirat
- **Expirată** — revizia a expirat sau este depășită
- **Nedefinit** — nu există date despre revizie în API

Atribute: Data ultimei revizii, Data ultimei verificări, Data următoarei inspecții, Tipul inspecției, Depășită.

---

## De ce entitățile au un nume lung, cu codul POC inclus?

[Înapoi la cuprins](#top)

Integrarea setează manual `entity_id`-ul fiecărei entități, incluzând codul POC, utilitatea și (pentru contor) nr. instalației. Formatul general este:

- `sensor.myengie_{poc}_{utilitate}_{tip_senzor}`
- `button.myengie_{poc}_{utilitate}_trimite_index`

De exemplu, pentru un POC `7002938475` cu utilitate gaz:
- `sensor.myengie_7002938475_gaz_sold_total`
- `sensor.myengie_7002938475_gaz_date_contract`
- `sensor.myengie_7002938475_gaz_factura_restanta`
- `button.myengie_7002938475_gaz_trimite_index`

Avantajul principal: dacă ai mai multe POC-uri cu mai multe utilități, fiecare entitate are un ID unic.

---

## Vreau să trimit indexul automat. De ce am nevoie?

[Înapoi la cuprins](#top)

Două lucruri:

**1. Entitate `input_number`** — Butonul de trimitere citește valoarea din `input_number`. Această entitate trebuie creată manual în `configuration.yaml`.

**2. Citire permisă = Da** — Trebuie să fii în perioada de autocitire.

Exemplu de automatizare:

```yaml
alias: "GAZ: Transmitere index automat ENGIE"
description: >-
  Trimite autocitirea în ziua 25 a fiecărei luni la ora 12:00.
triggers:
  - trigger: time
    at: "12:00:00"
conditions:
  - condition: template
    value_template: "{{ now().day == 25 }}"
  - condition: state
    entity_id: sensor.myengie_7002938475_gaz_citire_permisa
    state: "Da"
actions:
  - action: button.press
    target:
      entity_id: button.myengie_7002938475_gaz_trimite_index
```

---

## Ce e licența și de ce am nevoie de ea?

[Înapoi la cuprins](#top)

Integrarea folosește un sistem de licențiere server-side (v3.3) cu semnături Ed25519 și HMAC-SHA256. Fără o licență validă, integrarea afișează doar senzorul „Licență necesară" și nu creează senzori sau butoane funcționale.

Licența se achiziționează de la: [hubinteligent.org/licenta/myengie](https://hubinteligent.org/licenta/myengie)

După achiziție, introdu cheia de licență din OptionsFlow:
1. **Setări** → **Dispozitive și Servicii** → **MyENGIE România** → **Configurare**
2. Selectează **Licență**
3. Completează câmpul „Cheie licență"
4. Salvează

---

## Am introdus licența dar senzorii tot arată „Licență necesară". De ce?

[Înapoi la cuprins](#top)

Câteva cauze posibile:

1. **Licența nu a fost validată** — verifică logurile pentru mesaje cu `LICENSE`
2. **Serverul de licențe nu este accesibil** — dacă HA nu are acces la internet, validarea eșuează
3. **Cheie greșită** — verifică că ai copiat cheia corect, fără spații suplimentare
4. **Restartare necesară** — în rare cazuri, un restart al HA poate rezolva problema

Activează debug logging ([DEBUG.md](DEBUG.md)) și caută mesaje legate de licență.

---

## Am schimbat opțiunile integrării. Trebuie să restartez?

[Înapoi la cuprins](#top)

Nu. Integrarea se reîncarcă automat când salvezi modificările din OptionsFlow. Nu este necesar un restart manual al Home Assistant.

De asemenea, dacă modifici credențialele (email, parolă) din opțiuni, integrarea validează autentificarea înainte de a salva — dacă noile date sunt greșite, vei primi o eroare și configurația existentă rămâne neschimbată.

---

## Trebuie să șterg și readaug integrarea la actualizare?

[Înapoi la cuprins](#top)

De regulă nu. Setările sunt stocate în baza de date HA, nu în fișiere. Actualizarea suprascrie doar codul. Restartează Home Assistant după actualizare și integrarea continuă cu aceleași setări.

---

## Îmi place proiectul. Cum pot să-l susțin?

[Înapoi la cuprins](#top)

- Oferă un **star** pe [GitHub](https://github.com/cnecrea/myengie/)
- **Raportează probleme** — deschide un [issue](https://github.com/cnecrea/myengie/issues)
- **Contribuie cu cod** — trimite un pull request
- **Donează** prin [Buy Me a Coffee](https://buymeacoffee.com/cnecrea)
- **Distribuie** proiectul prietenilor sau comunității tale
