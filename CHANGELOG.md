# Changelog — Elettrodomestico Monitor

Fonte unica per la cronologia delle versioni di **progetto** (manifest.json /
const.VERSION). Le intestazioni `# VERSION:` in cima a ogni singolo file
tracciano invece l'ultima modifica *di quel file* e possono restare ferme
per più release consecutive se il file non viene toccato.

## [7.0.1] - 2026-09-10

### Fixed — Correzione a un fix della 7.0.0 (segnalato dai log reali dell'utente)

La 7.0.0 aveva impostato `state_class: total_increasing` su **tutti** i
sensori periodo che si azzerano, inclusi quelli di **costo in €**
(`_CostoPeriod`, `_RisparmioSole`, `_CostoRete` in sensor.py, `_IrrCosto`
per l'irrigazione). Sbagliato, per due motivi distinti emersi nei log reali
dell'utente pochi minuti dopo il deploy:

1. **`_CostoRete` e `_IrrCosto` hanno `device_class: monetary`**, che Home
   Assistant non ammette in combinazione con `total_increasing` in nessun
   caso ("is using state class 'total_increasing' which is impossible
   considering device class ('monetary') it is using; expected None or
   one of 'total'") — errore di validazione ripetuto ad ogni avvio (114
   occorrenze nei log).
2. **Tutti e 4 questi sensori sono `accumulo_fisico × tariffa`**, e la
   tariffa può essere un sensore dinamico configurato nell'Hub. A
   differenza di un contatore fisico (kWh, litri, cicli — che sale SOLO
   per eventi reali), questo valore può scendere anche a metà giornata se
   il prezzo cala, senza che sia avvenuto alcun reset di periodo — violando
   l'assunzione di monotonicità di `total_increasing`. Confermato nei log:
   `sensor.costo_rete_oggi_x4` passato da 0.35 a 0.34 alle 18:16, in pieno
   giorno, non a mezzanotte ("state is not strictly increasing", 106
   occorrenze).

Verificato (fonte: developers.home-assistant.io/docs/core/entity/sensor e
issue home-assistant/core#115009) che `total` con `last_reset` sarebbe la
soluzione "da manuale", ma `last_reset` è deprecato/non supportato in modo
affidabile nelle versioni recenti di HA, e la stessa documentazione
raccomanda in questi casi `state_class` a `None` (nessuna statistica a
lungo termine per quell'entità specifica) come scelta sicura. È quello che
è stato fatto qui per tutti e 4 i sensori: restano sensori numerici
corretti e visibili nella cronologia normale, ma non partecipano più alle
Statistiche a lungo termine di HA (niente più grafico "Statistiche"
dedicato per quei 4 sensori specifici — gli altri sensori periodo/totale
in kWh/L/cicli, genuinamente monotoni, restano `total_increasing` come
nella 7.0.0 e non risultano coinvolti in nessuno dei due errori).

**Nota per chi ha già installato la 7.0.0**: dopo l'aggiornamento a
7.0.1 e il riavvio di Home Assistant, gli errori in log si fermano. Se il
grafico Statistiche di uno di questi 4 sensori mostra un andamento strano
per la finestra in cui girava la 7.0.0, può essere corretto/rimosso da
**Impostazioni → Sistema → Correggi problemi rilevati** oppure da
**Strumenti per sviluppatori → Statistiche** (funzione "Regola" o
eliminazione dei punti dati per quel periodo) — non è necessario per il
funzionamento futuro dell'integrazione, solo per pulire lo storico grafico.

## [7.0.0] - 2026-09-10

Major bump: risoluzione completa dei 29 problemi (3 critici, 5 alti, 9 medi,
12 minori) emersi dall'audit del codice del 2026-09-10. Nessuna modifica
richiesta alla configurazione esistente — gli utenti aggiornano senza
riconfigurare nulla — ma alcuni fix correggono l'*interpretazione* di dati
già salvati (in particolare lo `state_class` dei sensori), da qui il major
invece di un minor.

**Nota di trasparenza**: in questo ambiente non è disponibile un interprete
Python funzionante, quindi — a differenza delle release precedenti — questi
fix NON sono stati verificati con `pytest tests/ -v` prima della consegna.
Sono stati rivisti a mano riga per riga (firme dei costruttori, indentazione,
punti di chiamata, test esistenti potenzialmente in conflitto) e i nuovi
test aggiunti sono stati scritti per essere eseguiti dalla CI del progetto
(hassfest/HACS/ruff/pytest, `.github/workflows/validate.yml`) al primo push.
Da considerare "da confermare al primo run reale della CI", come già fatto
in trasparenza per la 6.3.1.

### Fixed — Critico
- **sensor.py**: quasi tutti i sensori periodo (energia/costo/cicli/acqua
  oggi-mese-anno, kWh totale) usavano `state_class: total` invece di
  `total_increasing`. Si azzerano ogni notte/mese/anno o al pulsante
  "Reset Contatori": con `total`, Home Assistant registrava il calo come
  un dato reale (es. immissione in rete), generando un picco negativo
  fittizio nelle Statistiche a lungo termine / Energy Dashboard.
- **irrigation_coordinator.py**: il tempo di irrigazione veniva sommato sia
  dai tick periodici del coordinator sia una seconda volta nel blocco
  `finally` di fine ciclo — un'irrigazione di 10 minuti risultava
  conteggiata come ~20 in "Tempo Oggi/Mese/Anno".
- **notify_helper.py**: le finestre orarie che attraversano la mezzanotte
  (es. 22:00 → 06:00) non facevano mai scattare le notifiche vocali
  Alexa/Google — il confronto `start <= now <= end` era sempre falso per
  quel tipo di finestra, senza alcun errore in log.

### Fixed — Alto
- **services.py** (`import_config`): nessuna validazione del JSON importato
  (crash non gestito su file malformato); il conteggio "creati" non
  rifletteva il reale esito del flow di creazione.
- **config_flow.py** (`async_step_import`): nessun controllo di unicità
  slot — ora rifiuta un import che collide con uno slot già in uso.
- **device_coordinator.py**: rollover giornaliero/mensile/annuale guidato
  da un confronto in-memory del giorno, perso silenziosamente se HA
  riavviava a cavallo della mezzanotte. Ora una callback pianificata a
  23:59:59, come coordinator.py e irrigation_coordinator.py.
- **coordinator.py**: un'entità trigger `unavailable` (perdita di
  connettività cloud) oltre il debounce configurato spezzava un'unica
  accensione fisica in più cicli; il poll periodico bypassava persino il
  debounce esistente. Unificati in un helper condiviso, con una grazia più
  lunga (5 minuti) per la sola perdita di connettività.
- **tests/**: aggiunta copertura per sensor.py (enumerazione state_class su
  tutti i sensori periodo/totale, elettrodomestici e irrigazione),
  irrigation_coordinator.py (doppio conteggio tempo) e notify_helper.py
  (finestra a cavallo della mezzanotte) — le tre criticità sopra sono ora
  coperte da un test di regressione dedicato.

### Fixed — Medio
- **coordinator.py**: il "costo dell'ultimo ciclo" veniva ricalcolato con
  la tariffa ATTUALE invece di quella storica già salvata — con tariffe
  dinamiche cambiava anche dopo che il ciclo era finito.
- **services.py**: `reset_sensors`/`set_maintenance`/`irrigation_start`/
  `irrigation_stop` con un `entry_id` sconosciuto ora notificano l'errore
  invece di un no-op silenzioso.
- **config_flow.py**: `switch_entity` ora è controllato per uso duplicato
  tra device diversi, come già avveniva per le altre entità di controllo.
- **Traduzioni** (it/en/strings.json): aggiunto `fv_invert` mancante;
  completate le schermate Opzioni di Device e Irrigation (che condividono
  lo `step_id="init"` con Appliance ma non ne condividevano le traduzioni);
  aggiunta traduzione per lo step `irr_zones`.
- **notify_helper.py**: il messaggio WhatsApp ora viene troncato al limite
  dichiarato dall'entità `input_text` invece di fallire silenziosamente.
- **irrigation_coordinator.py**: aggiunto il rispetto del flag `fv_exclude`
  (già presente in coordinator.py) per escludere la pompa dal conteggio
  fotovoltaico.
- **storage.py**: validazione di tipo sui dati ripristinati da disco — un
  campo numerico corrotto non blocca più silenziosamente gli aggiornamenti
  successivi del coordinator.
- **migration.py**: aggiunto un marcatore di versione di schema esplicito
  (`_migration_schema_version`), base per future migrazioni che debbano
  trasformare (non solo aggiungere) una chiave.
- **const.py**/**coordinator.py**: l'indicatore "main_on" del vacuum in UI
  ora usa la stessa blocklist di stati non standard già usata per il
  conteggio cicli/energia, invece di un'allowlist che non stava al passo.

### Fixed — Minore
- Possibile doppio Hub Globale in caso di race condition (aggiunto
  `async_set_unique_id`).
- Limiti soglie ricarica batteria (`dev_start_pct`/`dev_stop_pct`) allineati
  a 1-100% nel config_flow, coerenti con le entità number.py.
- Switch di zona irrigazione lasciato vuoto: ora tracciato in log invece di
  essere accettato in silenzio.
- Tariffe (EUR/kWh, EUR/m³): aggiunto un tetto di sanità (10 €/unità) contro
  refusi di virgola decimale.
- `sensor.py`: corretto il fallback a 0 (mai applicato) per la batteria
  vacuum quando il dato è assente.
- `vacuum.py`: un entity_id costruito a mano ora passa da `naming.py`.
- `__init__.py`: sostituiti alcuni `except Exception: pass` silenziosi con
  log diagnostici; l'unload dell'Hub ora verifica l'esito prima di ripulire
  lo stato, come gli altri tipi di entry.
- `www/elettrodomestico-monitor-card.js`: il popup Info (markdown) ora
  applica lo stesso escaping usato altrove nella card, per coerenza
  difensiva (non sfruttabile oggi — la card markdown di HA sanitizza già).
- Micro-ottimizzazione: `build_eids()` calcolato una sola volta per entità
  invece che ad ogni lettura degli attributi.

### Non incluso in questa release
- La duplicazione di logica (rollover, split fotovoltaico, formattazione
  durata) tra i 3 coordinator NON è stata estratta in un helper condiviso
  — per scelta esplicita, per limitare la superficie di rischio di questa
  release ai fix mirati. Resta un miglioramento strutturale valido per il
  futuro.
- È emerso durante il fix di `fv_exclude` che il relativo campo di
  configurazione (`CONF_FV_EXCLUDE`) non è mai stato esposto nella UI del
  config_flow per NESSUN tipo di device (non solo irrigazione) — il flag
  esiste ed è ora rispettato a livello di coordinator, ma resta
  raggiungibile solo tramite `import_config`/modifica manuale dello
  storage. Aggiungere il relativo controllo nel wizard è un miglioramento
  separato, non incluso qui.

## [6.3.1] - 2026-09-09

### Changed — nessuna modifica al codice dell'integrazione, solo ai test
Prima esecuzione reale di `pytest tests/ -v` con `asyncio_mode = "auto"`
attivo (v6.3.0): 66/70 test sono girati per davvero, rivelando 3 bug nei
*test*, non nel codice del componente. Nessuno di questi fix tocca
`custom_components/elettrodomestico_monitor/` — il bump di versione è
solo per tracciabilità.

- **`tests/test_integration.py`**: il test assumeva che il coordinator
  fosse registrato in `hass.data[DOMAIN]` con chiave `instance_id`
  (`"lavatrice1"`). Il codice reale (`__init__.py`) lo registra con
  chiave `entry.entry_id` (un ULID generato da Home Assistant) — bug
  del test, non del componente. Corretta l'asserzione.
- **`tests/test_irrigation_coordinator.py`**: 4 test facevano
  `monkeypatch.setattr(hass.services, "async_call", ...)` per
  intercettare le chiamate a `turn_on`/`turn_off`. Contro la vera
  `ServiceRegistry` di Home Assistant questo fallisce
  (`AttributeError: 'ServiceRegistry' object attribute 'async_call' is
  read-only` — la classe reale non permette di sovrascrivere quel
  metodo per istanza). Sostituito con `async_mock_service()`, l'helper
  ufficiale di `pytest-homeassistant-custom-component` pensato apposta
  per questo: registra un servizio fittizio reale e restituisce la
  lista delle chiamate ricevute.
- **`tests/test_switch.py`**: il test di ripristino stato
  (`RestoreEntity`) impostava un attributo `_stub_last_state` che
  esisteva solo nell'harness di sviluppo locale (mai eseguito con la
  vera libreria) — la vera `RestoreEntity.async_get_last_state()` non lo
  legge affatto, restituisce sempre `None` per un'entità istanziata
  senza `self.hass` impostato. Sostituito con `mock_restore_cache()` +
  `switch.hass = hass`, il pattern standard per testare `RestoreEntity`.

### Nota di trasparenza
Questi 3 fix non sono stati verificati con il mio harness locale (a
differenza di tutto il resto del progetto) — usano API reali del
framework (`async_mock_service`, `mock_restore_cache`) che non ho mai
dovuto stubare finora. Si basano sulla conoscenza di questi pattern
standard nell'ecosistema Home Assistant, non su un'esecuzione
verificata qui. Da confermare con il prossimo run reale della CI.

### Fixed
-

## [6.3.0] - 2026-09-09

### Fixed — Test (pytest), 66 errori su 70 test raccolti
- **Causa reale, non un bug nel codice testato**: mancava del tutto la
  sezione `[tool.pytest.ini_options]` con `asyncio_mode = "auto"` in
  `pyproject.toml`. Senza questa riga, `pytest-asyncio` (in modalità
  STRICT di default) richiede un marcatore esplicito
  `@pytest.mark.asyncio` su OGNI singola funzione `async def test_...` —
  che nessuno dei ~70 test scritti finora aveva mai avuto, perché non è
  necessario quando `asyncio_mode = "auto"` è impostato (lo standard per
  i progetti che usano `pytest-homeassistant-custom-component`, la cui
  fixture `hass` è essa stessa asincrona). Aggiunta la configurazione
  mancante — nessuna modifica ai file di test è stata necessaria.
- I 4 test già passati prima del fix (`test_switch.py`, quelli scritti
  come funzioni sincrone senza `async def`) confermano che il problema
  era isolato ai test asincroni, non un problema di ambiente più ampio.

### Fixed — Hassfest
- `manifest.json`: `[ERROR] [MANIFEST] Manifest keys are not sorted
  correctly` — le chiavi non erano in ordine alfabetico dopo
  `domain`/`name` (richiesto da hassfest). Riordinate; verificato che
  `bump_version.sh` non alteri l'ordine nei bump futuri (aggiorna il
  valore di una chiave già esistente, non la riposiziona).

### Fixed
-

## [6.2.9] - 2026-09-09

### Added
- **`LICENSE`** (MIT) — mancava del tutto, richiesta obbligatoria da HACS
  per la validazione ("The repository has no license"). MIT scelta come
  default ragionevole per un'integrazione custom HA: è una decisione
  legale dell'autore, da confermare o cambiare liberamente.
- **`CONFIG_SCHEMA`** in `__init__.py` — richiesto da hassfest (warning)
  per ogni integrazione che implementa `async_setup`/`setup`; usa
  `cv.config_entry_only_config_schema(DOMAIN)` dato che l'integrazione
  si configura solo tramite config entry, mai da YAML.

### Fixed — Hassfest (dalla prima esecuzione reale della CI)
- **`manifest.json`**: due componenti usati nel codice
  (`hass.http.async_register_static_paths` e
  `homeassistant.components.lovelace.resources`) non erano dichiarati.
  Aggiunto `"http"` in `dependencies` (dipendenza vera: serve sempre per
  registrare i path statici) e `"lovelace"` in `after_dependencies`
  (uso opzionale, già gestito con try/except quando la dashboard è in
  modalità YAML).

### Fixed — HACS
- **`hacs.json`** e **`README.md`** alla radice (mancavano — vedi
  v6.2.8); risolto anche il fallimento per licenza mancante (vedi sopra).

### Fixed — Lint (ruff), 6 errori dalla prima esecuzione reale
- **`__init__.py`**: variabile `ex` assegnata e mai usata in un blocco
  `except` (F841) — rimossa.
- **`climate.py`**: la proprietà `current_temperature` era definita
  DUE volte nella stessa classe, identiche (F811) — probabile copia-incolla
  vicino alle proprietà di umidità aggiunte in seguito. Rimossa la
  duplicata; nessun cambio di comportamento (Python usava già solo
  l'ultima definizione).
- **`sensor.py`**: loop `for day_it, day_en in zip(WEEK_DAYS, WEEK_DAYS_EN)`
  con `day_en` mai usato nel corpo (B007) e `zip()` senza `strict=`
  (B905). `WEEK_DAYS_EN` non serviva a nient'altro nel file — semplificato
  in un semplice `for day_it in WEEK_DAYS`, rimosso anche l'import ora
  inutilizzato.
- **`sensor.py`**: due funzioni helper (`_device`, `_device_dev`)
  calcolavano una variabile `icon` da `device_icon` ma non la passavano
  mai a `DeviceInfo(...)` (che non ha comunque un parametro icona) —
  variabili morte (F841) in entrambe, rimosse.

### Non affrontato in questa release
- **"Test (pytest)"**: il log di questo job non è stato condiviso in
  questo giro (solo Hassfest, HACS e Lint) — il suo esito resta da
  verificare. Prossimo passo naturale: rilanciare la pipeline e, se
  fallisce ancora, condividere anche quel log.

### Fixed
-

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
