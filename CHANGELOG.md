# Changelog — Elettrodomestico Monitor

Fonte unica per la cronologia delle versioni di **progetto** (manifest.json /
const.VERSION). Le intestazioni `# VERSION:` in cima a ogni singolo file
tracciano invece l'ultima modifica *di quel file* e possono restare ferme
per più release consecutive se il file non viene toccato.

## [6.2.8] - 2026-09-09

### Added
- **`hacs.json`** alla radice del repo — mancava del tutto, causa quasi
  certa del fallimento "Validazione HACS" nella prima esecuzione reale
  della CI su GitHub.
- **`README.md`** alla radice del repo — mancava del tutto (esisteva solo
  una copia dentro `custom_components/elettrodomestico_monitor/`, con
  versione disallineata: 6.1.0 mentre il progetto era già a 6.2.7).
  HACS mostra il README della radice nella scheda del repository, quindi
  la sua assenza è un problema a sé, non solo estetico.
- **`custom_components/elettrodomestico_monitor/brand/icon.png`** — nuova
  cartella `brand/` con l'icona, seguendo il meccanismo nativo introdotto
  da Home Assistant 2026.3 (vedi
  https://developers.home-assistant.io/blog/2026/02/24/brands-proxy-api).

### Changed — pulizia in vista della pubblicazione HACS
- **`manifest.json`**: `after_dependencies` conteneva piattaforme generiche
  (`sensor`, `binary_sensor`, `button`, `number`, `text`, `switch`, `time`,
  `vacuum`) mescolate a vere integrazioni esterne. Le piattaforme non sono
  "integrazioni" da attendere — sono fornite anche dalla nostra stessa
  integrazione tramite `async_forward_entry_setups`. Rimosse; restano solo
  le dipendenze reali: `notify`, `tts`, `media_player`, `input_text`.
- **`__init__.py`**: rimossa la registrazione manuale del path HTTP
  `/brands/{DOMAIN}` (un workaround per il vecchio meccanismo CDN-based
  di brands.home-assistant.io). Da HA 2026.3+ le immagini in una cartella
  `brand/` dentro l'integrazione vengono servite automaticamente dal
  nuovo sistema nativo — nessuna registrazione manuale necessaria.
  Rimosso anche il vecchio `icon.png` alla radice del componente (non più
  referenziato da nessun path, sostituito da `brand/icon.png`).
- **`custom_components/elettrodomestico_monitor/README.md`** rimosso
  (duplicato della radice — è quello che ha causato la versione
  disallineata segnalata dall'utente).
- **`bump_version.sh`**: aggiunta la sincronizzazione automatica della
  riga "**Versione:**" in `README.md` (radice) ad ogni bump — prima
  andava aggiornata a mano ed è proprio così che si era disallineata.
  Verificato con test end-to-end, incluso il caso limite in cui la riga
  versione non fosse presente (avvisa senza bloccare lo script).

### Non affrontato in questa release — servono i log reali
- I fallimenti di **Hassfest**, **Lint (ruff)** e **Test (pytest)** nella
  CI reale non sono stati diagnosticati: l'immagine allegata mostra solo
  l'esito (✗/✓), non il testo dell'errore. Il fix di `after_dependencies`
  potrebbe risolvere Hassfest (è la causa più plausibile), ma senza il
  log non è verificabile con certezza. Lint e Test non erano mai stati
  eseguiti con il vero `ruff`/`pytest-homeassistant-custom-component`
  (nessun accesso di rete disponibile in fase di sviluppo) — è la prima
  esecuzione reale e ha trovato problemi che l'ambiente di sviluppo non
  poteva vedere. Richiesto il testo completo di questi tre job per
  procedere.

### Fixed
-

## [6.2.7] - 2026-09-07

### Changed — su richiesta dell'utente, correzione a v6.2.6
- **`www/elettrodomestico-monitor-card.js`**: il lampeggio introdotto in
  v6.2.6 applicava la classe `has-update` a ENTRAMBI i pulsanti Update
  (🔔) e Info (ℹ️). L'utente ha chiarito di volerlo solo sulla
  campanellina Update — rimosso da Info.

### Fixed
-

## [6.2.6] - 2026-09-07

### Added
- **`tests/test_update_sensor.py`**: verifica che lo stato del sensore
  aggiornamento includa il tag di versione trovato su GitHub, invece del
  testo generico precedente.
- Nuova animazione `has-update` in `elettrodomestico-monitor-card.js`:
  i pulsanti "Update" (🔔) e "Info" (ℹ️) lampeggiano quando è disponibile
  un aggiornamento, come indicazione persistente sulla card (la notifica
  push arriva una volta sola e si dimentica facilmente).

### Changed — richiesta utente: versione visibile + indicazione persistente
- **`sensor.py` — `_UpdateSensor.native_value`**: prima mostrava sempre
  il testo fisso "Aggiornamento disponibile", senza indicare quale
  versione — l'informazione (`versione_disponibile`) era già letta da
  GitHub e disponibile come attributo, semplicemente non veniva mai
  inclusa nello STATO del sensore (quello che il popup Info della card
  mostra). Ora lo stato è "Aggiornamento disponibile v6.2.6" (o il tag
  trovato), con fallback difensivo al testo generico se il tag non fosse
  ancora disponibile.
- **`www/elettrodomestico-monitor-card.js`**: aggiunta la classe
  `has-update` (animazione di lampeggio arancione) applicata/rimossa sui
  pulsanti Update e Info ad ogni refresh della card, leggendo l'attributo
  booleano `aggiornamento` del sensore hub. Ho scelto di far lampeggiare
  ENTRAMBI i pulsanti (non solo "Info" come richiesto letteralmente)
  perché "Update" (🔔) è il pulsante già dedicato proprio a questo scopo
  — se non era abbastanza visibile da solo, probabilmente serviva lo
  stesso trattamento su entrambi.

### Fixed
-

## [6.2.5] - 2026-08-30

### Added
- Test di regressione per `irrigation_coordinator.py`
  (`test_cycle_notification_shows_cycle_grid_split_not_daily_total`),
  stesso schema del test aggiunto in v6.2.4 per coordinator.py.

### Fixed — irrigation_coordinator.py: stesso bug di v6.2.4, non coperto allora
- L'utente ha chiesto esplicitamente se il fix della notifica Rete/Sole
  (v6.2.4) copriva **tutti** i tipi di dispositivo, inclusa
  l'irrigazione. Non li copriva: `irrigation_coordinator.py` è un
  coordinator completamente separato, con una propria
  `_notify_complete()` che aveva lo stesso identico bug — leggeva
  `costo_rete_oggi`/`risparmio_sole_oggi` (il cumulativo di tutta la
  giornata) invece della quota del solo ciclo di irrigazione appena
  concluso. Stesso fix applicato: snapshot di energia rete/sole
  all'inizio del ciclo, delta calcolato a fine ciclo. Verificato con
  esecuzione reale, incluso un caso rigoroso con energia realmente
  diversa da zero aggiunta a metà ciclo (per escludere una verifica
  debole del tipo 0=0).

### Verificato per completezza — nessun altro caso da correggere
- **Elettrodomestici standard, acqua, gas, generico**: usano lo stesso
  `coordinator.py` già corretto in v6.2.4 — coperti.
- **Clima**: passa per lo stesso step di configurazione generico degli
  elettrodomestici standard (non ha un flusso dedicato come vacuum) — se
  configurato con un sensore di potenza reale, usa lo stesso codice già
  corretto in v6.2.4; se configurato solo con `trigger_entity` (senza
  sensore di potenza), non traccia energia affatto — comportamento
  preesistente, non introdotto né modificato da questo fix.
- **Vacuum**: usa lo stesso `coordinator.py` corretto — il fix è
  strutturalmente applicato, ma dato il bug noto e non ancora risolto
  per cui il vacuum non ha mai un sensore di potenza reale (vedi
  CHANGELOG v6.2.3), la quota rete/sole del ciclo resta comunque sempre
  0/0 — nessun miglioramento visibile finché quel problema separato non
  viene affrontato.
- **Dispositivo/batteria**: `device_coordinator.py` non ha mai avuto una
  riga "Rete"/"Sole" in nessuna notifica — non fa tracking di
  energia/costo per design (confermato in v6.2.3). Nulla da correggere.

## [6.2.4] - 2026-08-29

### Added
- Test di regressione (`test_cycle_notification_shows_cycle_grid_split_not_daily_total`)
  che riproduce esattamente lo scenario segnalato da un utente reale:
  un ciclo alimentato interamente da accumulo/batteria che mostrava
  comunque un costo "Rete" diverso da zero in notifica.

### Fixed — coordinator.py: notifica di fine ciclo, split Rete/Sole errato
- **Segnalato da un utente reale**: un ciclo (macchina del caffè)
  alimentato interamente da accumulo/batteria — quindi 0€ di prelievo
  rete per QUEL ciclo — mostrava comunque una notifica con "Rete: 0.02€
  Sole: 0.01€" pur avendo "Costo: 0.01€" (i tre numeri non tornavano:
  0.02+0.01 ≠ 0.01). Causa: `_notify()` leggeva `costo_rete_oggi` e
  `risparmio_sole_oggi` — il cumulativo di **tutta la giornata** — mentre
  `consumo`/`costo` nella stessa notifica erano correttamente calcolati
  per il solo ciclo appena concluso. Se l'utente aveva usato la rete
  anche solo minimamente PRIMA in giornata (es. un caffè precedente),
  quella cifra compariva nella notifica del ciclo successivo anche se
  quel ciclo specifico non aveva toccato la rete.
  Riprodotto con i numeri esatti riportati dall'utente: con 0.08 kWh di
  rete e 0.04 kWh di sole già accumulati oggi PRIMA di questo caffè, il
  vecchio codice avrebbe mostrato Rete=0.02€/Sole=0.01€ per QUALSIASI
  ciclo successivo, indipendentemente dalla sua fonte reale — una
  corrispondenza pressoché esatta con la segnalazione.
  **Fix**: aggiunto uno snapshot di energia rete/sole all'inizio del
  ciclo (`cycle_start_eg`/`cycle_start_es`, stesso pattern già usato per
  il consumo totale del ciclo, `cycle_start_kwh`); a fine ciclo si
  calcola il delta rispetto a quello snapshot, non il cumulativo di
  giornata. Persistito in storage per sopravvivere a un riavvio di HA a
  metà ciclo.

## [6.2.3] - 2026-07-28

### Added
- **`tests/test_device_coordinator.py`**: primo test per
  `device_coordinator.py` (mai testato finora). 5 scenari: avvio carica
  sotto soglia, nessun doppio conteggio cicli mentre resta sotto soglia,
  stop sopra soglia, e i due scenari che hanno rivelato il bug corretto
  in questa release (soglie invertite, soglie identiche).
- Test di regressione per il fix del costo settimanale storico
  (`test_weekly_cost_uses_historical_price_not_current`) e per la
  retrocompatibilità con dati salvati prima del fix.

### Fixed — coordinator.py: costo storico settimanale
- Il costo mostrato per un giorno passato nella tabella settimanale
  (Lunedì...Domenica) veniva **sempre ricalcolato con il prezzo €/kWh
  ATTUALE**, scartando il valore corretto già salvato in storage con il
  prezzo in vigore quel giorno. Per un prezzo fisso è invisibile (non
  cambia mai); per chi usa un sensore di costo dinamico, il costo di
  "Lunedì" cambiava ogni volta che il prezzo di OGGI cambiava.
  Dimostrato con esecuzione reale: 10 kWh a 0,20€/kWh salvavano
  correttamente 2,00€, ma mostravano 5,00€ il giorno dopo se il prezzo
  saliva a 0,50€. Ora si legge il valore storico salvato; il ricalcolo
  resta solo come fallback per dati salvati prima di questo fix.

### Fixed — device_coordinator.py: soglie di carica invertite
- Nessuna validazione impediva di impostare la soglia di avvio >= quella
  di stop, né in config_flow né modificando i number entity dinamici in
  dashboard (che non hanno validazione incrociata). Confermato con
  esecuzione reale: questa configurazione causava un toggling ON/OFF
  continuo ad ogni aggiornamento (6 cambi di stato su 6 update),
  gonfiando il conteggio cicli e generando notifiche a raffica. Ora il
  controllo automatico si sospende con un warning invece di comportarsi
  in modo imprevedibile, quando le soglie sono invertite o coincidenti.

### Trovato ma NON corretto — richiede una decisione di design
- **Preset vacuum: consumo e costo sono sempre 0€, in ogni ciclo.**
  `_integrate()` si rifiuta di accumulare energia per qualunque
  dispositivo privo di un sensore di potenza reale, e il vacuum non ne
  ha mai uno per come è strutturato il config_flow (usa `vacuum_entity`
  come trigger, azzera esplicitamente `power_sensor`). Confermato
  simulando un ciclo di pulizia completo di 30 minuti: consumo e costo
  restano 0.0 in ogni caso, non solo in casi limite. Non corretto in
  questa release: richiede una scelta tra (a) aggiungere un campo
  "potenza media stimata" al config_flow del vacuum per calcolare il
  costo da tempo×potenza assunta, o (b) nascondere i campi costo per
  questo preset invece di mostrare sempre 0€.
- **Preset "dispositivo/batteria": nessun bug nei calcoli** — verificato
  che instrada a `device_coordinator.py`, che non fa tracking di
  energia/costo per design (solo % batteria e cicli). Non c'era nulla
  da correggere sul fronte costi; il fix di questa release riguarda la
  robustezza delle soglie, non un calcolo sbagliato.

## [6.2.2] - 2026-07-23


### Added
- **`tests/test_switch.py`**: switch.py non era mai stato auditato. Audit
  a lettura completa: nessun bug funzionale trovato (solo una costante
  importata ma non usata, innocua). 11 test su `_MainSwitch` (lettura
  main_on/ac_state/default), persistenza `_NotifySwitch` dopo riavvio,
  `_DevChargeSwitch`, e la logica di dispatch che decide se creare il
  comando principale.
- **`tests/test_irrigation_coordinator.py`**: 8 scenari — rifiuto cicli
  concorrenti, sequenza zone nell'ordine di `zone_order` (non l'ordine
  di definizione), comportamento `manual=True`, ciclo interrotto non
  conteggiato, integrazione litri solo durante un ciclo attivo.
  `asyncio.sleep` monkeypatchato a zero (il ciclo reale impone un minimo
  di 10s per zona) per non rallentare la suite.
- **`tests/test_integration.py`**: primo test end-to-end (setup Hub +
  Appliance, verifica entità create). A differenza di tutti gli altri
  file di test di questo progetto, **non è stato eseguito con successo
  in un harness locale prima della consegna** — richiede la macchina
  reale di forwarding delle piattaforme di Home Assistant, che
  replicare in uno stub avrebbe significato reimplementare gran parte
  del core. Segue il pattern standard raccomandato da
  pytest-homeassistant-custom-component, ma è l'unico test di questa
  sessione da verificare per la prima volta in un ambiente reale.

### Fixed — sensor.py (audit completo delle ~900 righe non ancora
### riverificate)
- Nessun altro bug trovato con lo stesso pattern di quello corretto in
  6.2.1 (chiave dati derivata da un periodo nella lingua sbagliata):
  verificato che elettrodomestici standard, dispositivo/batteria e
  vacuum passano tutti la chiave dati esplicitamente invece di
  derivarla — pattern sicuro, a differenza di come erano scritte
  `_IrrCosto`/`_LitreSensor` prima del fix precedente.

### Fixed — coordinator.py (i 2 limiti noti rimasti dalla fase 2)
- **Race condition master/slave su sensore condiviso**: prima, quando
  due dispositivi condividevano lo stesso sensore di potenza fisico,
  solo il coordinator con l'instance_id più basso ("master") calcolava
  la ripartizione ad ogni proprio update, scrivendola sugli altri
  ("slave"). Se il dispositivo attivo cambiava esattamente tra un
  update del master e uno slave, quest'ultimo poteva restare fino a un
  intero intervallo di polling (`COORDINATOR_UPDATE_INTERVAL`, 20s)
  indietro. Ora ogni coordinator ricalcola la propria quota in modo
  indipendente al proprio turno, leggendo lo stato "attivo" fresco di
  tutto il gruppo — nessuna dipendenza dal tick di un altro coordinator.
  Verificato con esecuzione reale: lo slave vede ora il valore corretto
  immediatamente al proprio update, non più al giro successivo del
  master.
- **Ritardo ~5s nello stato "ciclo terminato"**: `_cycle_end()`
  pubblicava `self.data` (letto da tutte le entità) solo DOPO un
  `asyncio.sleep(5)` esplicito — per quella finestra le entità
  mostravano ancora "In funzione" con un timer in scorrimento anche se
  il dispositivo era già spento. Ora lo stato finale del ciclo
  (`cycle_active=False` + durata/consumo/costo) viene pubblicato subito
  dopo essere stato scritto in storage, prima di sparare l'evento e
  inviare la notifica. Il reset di `_cycle_start_ts`/`_cycle_start_acc`
  resta dopo il delay originale (verificato innecuo: quei due valori non
  vengono più letti da `_build()` una volta che il ciclo è inattivo).
  Verificato con esecuzione reale: `coordinator.data` riflette
  `cycle_active=False` entro 50ms dall'inizio di `_cycle_end()`, non più
  dopo 5 secondi pieni.

### Fixed — translations/en.json
- Il file era quasi interamente in italiano nonostante il nome
  `en.json` (solo alcuni step aggiunti più di recente erano già in
  inglese). Tradotto per intero, verificando che la struttura delle
  chiavi resti identica a `it.json` (nessuna chiave persa o aggiunta).

### Nessun problema residuo noto
Con questa release, tutti i punti dell'audit fase 2 rimasti aperti sono
stati affrontati: test su switch.py/irrigation_coordinator.py, audit
sensor.py completo, entrambi i limiti noti di coordinator.py corretti,
un primo test di integrazione end-to-end (da verificare in ambiente
reale), traduzioni inglesi corrette.

## [6.2.1] - 2026-07-22

### Added
- **`tests/test_config_flow.py`**: 9 scenari — validazione `flow_sensor`
  nello step irrigazione (vuoto, inesistente, valido), controllo
  duplicati per `vacuum_entity`/`trigger_entity`/`dev_battery_sensor`
  su nuova entry e in modifica (options flow, con esclusione corretta
  dell'entry stessa), test di non-regressione dedicato a verificare che
  la condivisione di `power_sensor` tra due dispositivi NON generi mai
  un errore (è una feature intenzionale, non un conflitto).

### Fixed — config_flow.py (punti 2 e 3 richiesti)
- Lo step irrigazione non verificava che `flow_sensor` (campo
  obbligatorio) corrispondesse a un'entità realmente esistente —
  incoerente con vacuum/dispositivo, che quella verifica la fanno già.
- Nessuno step verificava se un'entità di controllo (`vacuum_entity`,
  `trigger_entity`, `dev_battery_sensor`, `dev_charge_switch`) fosse già
  assegnata a un'altra config entry. Aggiunto un controllo dedicato
  (nuova costante errore `entity_in_use`) su: creazione vacuum, modifica
  vacuum (options flow), creazione appliance/climate, modifica appliance
  (options flow), creazione dispositivo/batteria. Il sensore di potenza
  resta volutamente escluso (condivisione intenzionale, vedi
  master/slave in coordinator.py) — coperto da test di non-regressione
  dedicato.
- Corretto durante l'implementazione un errore mio: un primo tentativo
  di patch aveva accidentalmente cancellato la definizione della
  funzione `_used_slots()` esistente — trovato subito dall'harness di
  verifica reale prima di consegnare, non arrivato nello zip.

### Fixed — bug segnalati dopo l'uso reale in produzione (v6.2.0)
- **`sensor.py`**: `_LitreSensor` e `_IrrCosto` (sensori dedicati
  litri/costo per l'irrigazione — oggi/mese/anno) costruivano la propria
  chiave di lettura dati usando il periodo in inglese ("today"/"month"/
  "year") invece del suffisso italiano — mentre `irrigation_coordinator.py`
  popola il dizionario con chiavi italiane ("litri_mese", "costo_rete_mese",
  ecc.). Il risultato: questi sensori dedicati mostravano SEMPRE 0,
  indipendentemente dal valore reale (bug segnalato: "Costo Rete mese
  Irrigazione siepe" a 0 mentre la card mostrava il valore corretto).
  Verificato con dati realistici prima e dopo il fix.
- **`www/elettrodomestico-monitor-card.js`**: le righe "Periodi
  Precedenti" (Ieri/Mese Prec./Anno Prec.), sia per irrigazione che per
  elettrodomestici standard, non hanno mai un sensore dedicato per quello
  specifico valore storico — prima il click su quelle celle ripiegava
  silenziosamente sul sensore aggregato `time_on`, aprendo il grafico
  sbagliato (bug segnalato: click su un costo "Periodi Precedenti" apriva
  "Time On... in ore"). Disabilitato esplicitamente il click (`noClick`)
  per queste celle invece di mostrare un grafico non pertinente — non
  esistendo un sensore storico dedicato, non c'è un grafico "corretto" da
  mostrare per un valore congelato di un periodo passato.

### Deferito
- Non sono stati creati nuovi sensori dedicati per i valori "Periodi
  Precedenti" (richiederebbe modifiche a `irrigation_coordinator.py` e
  `coordinator.py` per tracciarli come entità proprie, non solo come
  attributi) — la scelta fatta qui è disabilitare un click fuorviante,
  non inventare un grafico per un dato che nel modello attuale è un
  singolo valore congelato, non una serie storica.

## [6.2.0] - 2026-07-22

### Added
- **`tests/test_coordinator.py`**: 18 scenari su `coordinator.py` (soglia
  di lavoro, integrazione kWh, split fotovoltaico rete/sole incluso
  `unknown`/`unavailable`/inversione sensore/esclusione per-device, reset
  giornaliero/mensile/annuale, caso limite del ciclo aperto a mezzanotte,
  condivisione di un sensore di potenza tra più dispositivi).

### Fixed — sicurezza (XSS stored nelle card Lovelace)
- **`www/elettrodomestico-monitor-card.js`**: il nome configurato dalla
  card (`_config.name`, testo libero spesso copiato da dashboard
  condivise online) veniva interpolato senza escape in `innerHTML`. Un
  nome contenente markup (es. `<img src=x onerror=...>`) avrebbe eseguito
  come HTML/JS nel contesto della dashboard. Aggiunto un helper di escape
  e applicato al punto di interpolazione.
- **`www/elettrodomestico-dispositivo-card.js`**: stesso problema, due
  punti — il nome del dispositivo nell'header e l'entity_id nel messaggio
  "Entità non trovata".
- **`www/em-stat-table.js`**: titolo, header di colonna e valori di cella
  con `cell.raw` (testo libero, es. nomi zona) interpolati senza escape.
  Componente generico riusabile da configurazione YAML: il rischio reale
  dipende da cosa l'utente sceglie di mostrarci, ma qualunque attributo
  testuale configurato come sorgente andava in `innerHTML` senza
  sanificazione.
- Verificato con Node.js che la funzione di escape neutralizza un payload
  reale (`<img src=x onerror=alert(1)>`) lasciando invariato il testo
  normale (incluse lettere accentate italiane).

### Audit — nessun fix di codice applicato, solo osservazioni (vedi
### riepilogo finale in chat per i dettagli)
- `coordinator.py`: documentato (con test dedicato) un limite di
  consistenza reale, non un crash: quando due dispositivi condividono lo
  stesso sensore di potenza fisico, il device "slave" può restare fino a
  un intero intervallo di polling indietro rispetto al "master" se
  l'attivo cambia proprio a cavallo tra i due update — nessun lock né
  garanzia d'ordine tra i coordinator.
- `coordinator.py`: `_cycle_end()` mostra per ~5+ secondi uno stato
  incoerente (`ac_state=False` ma `cycle_active` ancora `True` con timer
  in scorrimento) perché `self.data` viene ripubblicato solo dopo un
  `asyncio.sleep(5)` esplicito. Difetto UX confermato con esecuzione
  reale, non ancora corretto.
- `config_flow.py`: il flusso di irrigazione non verifica che
  `flow_sensor` (campo obbligatorio) corrisponda a un'entità realmente
  esistente — a differenza degli step vacuum/dispositivo, che validano
  l'entità con `hass.states.get(...)`. Incoerenza di validazione tra step
  dello stesso file.
- `config_flow.py`: nessuno step verifica se un'entità di controllo
  (`switch_entity`, `vacuum_entity`, `trigger_entity`, `battery_sensor`)
  è già assegnata a un'altra config entry — solo lo slot numerico viene
  controllato per l'unicità. Il sensore di potenza fa eccezione
  intenzionalmente (è pensato per essere condiviso, vedi logica
  master/slave in coordinator.py), ma per le altre entità di controllo
  due dispositivi diversi potrebbero puntare silenziosamente alla stessa
  entità.
- `irrigation_coordinator.py`: letto per intero — logica di sequenza
  zone solida (blocco `finally` che garantisce lo spegnimento di tutte
  le zone, distinzione corretta tra ciclo completato/interrotto). Unica
  osservazione: il flag `manual=True` in `start_cycle()` sopprime
  l'accensione dello switch per OGNI zona nel ciclo, non solo per la
  prima — oggi non è raggiungibile come bug reale perché ogni chiamata
  con `manual=True` passa sempre anche uno `zone_idx` specifico (ciclo di
  una sola zona), ma è un'assunzione implicita fragile da tenere a mente
  se in futuro si aggiungerà un punto di chiamata multi-zona con
  `manual=True`.

### Deferito (onestamente non coperto in questa fase — vedi riepilogo
### finale in chat per il dettaglio)
- Nessun fix di codice per i tre punti di audit sopra (solo osservazioni
  documentate): richiedono una decisione di design (serializzazione tra
  coordinator condivisi, rimozione o accorciamento dello sleep(5),
  validazione entità irrigazione, controllo duplicati tra entità di
  controllo) prima di poter scrivere un fix verificato.
- Nessun test automatico per `config_flow.py`, `irrigation_coordinator.py`,
  `sensor.py`, `switch.py`.
- Nessun test di integrazione end-to-end (setup hub + appliance figlio →
  verifica entità create).

## [6.1.0] - 2026-07-20

### Fixed
- **migration.py**: rimosso un blocco di ~55 righe duplicato e irraggiungibile
  dopo il `return True` finale di `async_migrate_entry()`. Non causava un
  crash all'avvio (il parser Python lo accettava comunque), ma era dead code
  mai eseguito — la logica realmente attiva usava stringhe hardcoded
  (`"vacuum"`, `"clima"`) invece delle costanti centralizzate `PRESET_VACUUM`
  / `PRESET_CLIMA` già definite in `presets.py`. Unificata in un'unica
  implementazione che usa le costanti.
- **const.py**: l'header dichiarava `VERSION: 6.0.0` mentre la costante
  `VERSION` nel corpo del file era già `"6.0.4"`. Allineati entrambi alla
  versione di progetto corrente.

### Changed
- **manifest.json**: versione di progetto `6.0.4` → `6.1.0`.
- Aggiunto il campo `CHANGED` mancante nell'header di `device_coordinator.py`,
  `naming.py`, `notify_helper.py` (erano gli unici 3 file senza questa riga).
- README.md: versione dichiarata allineata da `5.7.0` (obsoleta) a `6.1.0`.
- Rimossa la cartella `__pycache__/` dal pacchetto distribuito (bytecode
  compilato, non va versionato né distribuito).

### Audit eseguito (nessun altro problema bloccante trovato)
- Verifica sintattica (`ast.parse`) su tutti i 24 moduli `.py`: OK.
- Scansione automatica per `except:` nudi, mutable default arguments,
  dict con chiavi duplicate, marker `TODO`/`FIXME`/`XXX`: nessun riscontro.
- Il meccanismo di cache-busting delle card Lovelace (`__init__.py`,
  `_register_one_resource`) è correttamente centralizzato su
  `const.VERSION` — bump della versione di progetto è sufficiente,
  non richiede modifiche sparse nei file `.js`.

### Added — tooling di sviluppo
- **`tests/`**: primo test automatico del progetto, mirato su
  `migration.py` (il modulo più delicato: gira ad ogni avvio, in modo
  silenzioso, per ogni config entry). 8 scenari con
  `pytest-homeassistant-custom-component`: entry Hub non toccato,
  riempimento chiavi mancanti con preservazione dei valori custom, entry
  già completo che non genera scritture inutili, auto-popolamento
  `vacuum_entity`, mismatch preset vacuum/clima (solo warning, mai
  eccezione), eccezione interna che non deve mai propagarsi e bloccare
  l'avvio.
- **`.github/workflows/validate.yml`**: CI con hassfest (validazione
  manifest/struttura integrazione), validazione HACS, lint `ruff`
  (scope iniziale: solo errori reali — sintassi, pyflakes, bugbear — non
  stile, per non generare rumore su codice mai lintato), un check
  dedicato che confronta `manifest.json` e `const.VERSION` (avrebbe
  intercettato automaticamente l'incoerenza sistemata a mano in questa
  release), ed esecuzione di `pytest`.
- **`bump_version.sh`**: script per aggiornare in un colpo solo
  `manifest.json` + `const.py` + uno stub in cima al `CHANGELOG.md`.
  Rifiuta di procedere se i due file versione risultano già
  disallineati prima del bump (segno che qualcuno li ha toccati a mano
  bypassando lo script).
- **`.gitignore`**: esclude `__pycache__/` e affini (uno dei problemi
  trovati nell'audit precedente).
- Repo riorganizzato in layout standard `custom_components/elettrodomestico_monitor/`
  a livello di root, necessario per hassfest/HACS e per l'import dei test.

### Nota sul versioning per-file
Da questa release, la policy è:
- `# VERSION:` nell'header di un file cambia **solo** quando quel file
  viene effettivamente modificato (non segue automaticamente la versione
  di progetto).
- `# CHANGED:` riporta la data dell'ultima modifica reale a quel file.
- Il changelog di progetto (questo file) resta l'unico posto dove cercare
  "cosa è cambiato nella versione X" a livello di release.
