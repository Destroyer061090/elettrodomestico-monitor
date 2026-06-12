# Elettrodomestico Monitor

Custom integration per Home Assistant per monitorare elettrodomestici, vacuum, clima e irrigazione.

**Versione:** v5.0 | **HA minima:** 202v5.0 | **Repository:** github.com/Destroyer061090/elettrodomestico-monitor

---

## Installazione

1. Copia la cartella `elettrodomestico_monitor` in `/config/custom_components/`
2. Riavvia Home Assistant
3. Vai in **Impostazioni → Integrazioni → Aggiungi** → cerca "Elettrodomestico Monitor"
4. Configura l'Hub Globale (costi, notifiche, orari)
5. Aggiungi device uno alla volta o tramite Import

---

## Tipi di Device (Preset)

| Preset | Unità | Uso tipico |
|--------|-------|-----------|
| Elettrodomestico | W → kWh | Lavatrice, lavastoviglie, forno |
| Acqua | L/min → L | Boiler, addolcitore |
| Gas | m³/h → m³ | Caldaia, cucina |
| Vacuum | — | Robot aspirapolvere (Roomba, K2T) |
| Clima | W → kWh | Split, pompa di calore |
| Irrigazione | L/min → L + W → kWh | Irrigazione con pompa sommersa |
| Generico | personalizzabile | Qualsiasi altro device |

---

## Servizi HA disponibili

### `elettrodomestico_monitor.export_config`
Esporta la configurazione di tutti i device in `/config/www/em_export.json`.
Scaricabile da browser all'indirizzo `/local/em_export.json`.
```yaml
service: elettrodomestico_monitor.export_config
```

### `elettrodomestico_monitor.import_config`
Importa la configurazione da un file JSON. Aggiorna i device esistenti (match per slot) o ne crea di nuovi.
```yaml
service: elettrodomestico_monitor.import_config
data:
  filename: em_export.json  # opzionale, default: em_export.json
```

### `elettrodomestico_monitor.remove_all_devices`
Rimuove tutti i device lasciando solo l'Hub. Utile prima di un import completo da zero.
```yaml
service: elettrodomestico_monitor.remove_all_devices
```

### `elettrodomestico_monitor.reset_sensors`
Azzera i contatori di un device specifico.
```yaml
service: elettrodomestico_monitor.reset_sensors
data:
  entry_id: "abc123..."  # entry_id del device
```

### `elettrodomestico_monitor.set_maintenance`
Registra una data di manutenzione per un device.
```yaml
service: elettrodomestico_monitor.set_maintenance
data:
  entry_id: "abc123..."
  note: "Sostituzione filtro"  # opzionale
```

---

## Workflow Import/Export

**Rinominare device (da "Nome (xN)" a "(xN) Nome"):**
1. `export_config` → scarica `/local/em_export.json`
2. Modifica il JSON: cambia i valori `"title"` 
3. Carica il file modificato in `/config/www/em_export.json`
4. `import_config` → i titoli vengono aggiornati
5. Riavvia HA

**Reset completo e riconfigurazione:**
1. `export_config` → backup della configurazione
2. `remove_all_devices` → rimuove tutti i device
3. Modifica il JSON se necessario
4. `import_config` → ricrea tutti i device
5. Riavvia HA

---

## Slot Convention consigliata

| Range | Tipo |
|-------|------|
| x1–x99 | Elettrodomestici standard |
| x100–x199 | Acqua / Gas / Boiler |
| x200–x209 | Vacuum |
| x210–x219 | Clima |
| x220–x229 | Irrigazione |
| x300+ | Meteo / Sensori |

---

## Card Lovelace JS

La card viene registrata automaticamente in Lovelace al riavvio HA.
Documentazione completa: `www/CARD_CONFIG.md`

**Configurazione minima:**
```yaml
type: custom:elettrodomestico-monitor-card
slot: 1
name: Lavastoviglie
```

**Con immagini:**
```yaml
type: custom:elettrodomestico-monitor-card
slot: 1
name: Lavastoviglie
image_on: /local/foto-pkg/lavastoviglie_on.gif
image_off: /local/foto-pkg/lavastoviglie_off.png
max_power: 2200
```

---

## Irrigazione con pompa sommersa

Configura come preset **Irrigazione** con:
- **Sensore portata** (`power_sensor`): es. `sensor.invertekoptidrivee3_flow_rate` (L/min)
- **Sensore pompa** (`power_sensor_2`): es. `sensor.invertekoptidrivee3_power_sensor` (W)
- **Switch** (`switch_entity`): es. `switch.switch_totale` (opzionale)

Il component traccia separatamente:
- Litri consumati (dal sensore portata)
- kWh pompa (dal sensore potenza)
- Costo acqua (€/m³ dall'Hub)

---

## Entità create per device

Ogni device crea automaticamente:
- `sensor.time_on_elettrodomestici_xN` — sensore master con tutti gli attributi
- `sensor.potenza_elettrodomestici_w_xN` — potenza/flusso istantaneo
- `sensor.energy_oggi/mese/anno_xN` — consumi periodici
- `sensor.cicli_oggi/mese/anno/totale_xN` — contatori cicli
- `sensor.costo_oggi/mese/anno_xN` — costi periodici
- `binary_sensor.ac_elettrodomestici_xN` — stato ciclo ON/OFF
- `switch.switch_elettrodomestici_xN` — comando principale
- `time.orario_accensione/spegnimento_xN` — orari automatici
- `vacuum.elettrodomestici_xN` — solo preset Vacuum
- `climate.elettrodomestici_xN` — solo preset Clima

---

## Note

- **Icona custom component**: non visibile nella pagina integrazioni HA (limitazione HA per custom component non nel registro ufficiale)
- **Risorsa JS**: registrata automaticamente con versioning (`?v=X.XX`) per evitare cache browser
- **Migration**: al riavvio HA verifica e aggiorna automaticamente i config entry con chiavi mancanti (non distruttivo)
