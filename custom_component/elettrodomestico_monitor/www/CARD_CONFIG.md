# Elettrodomestico Monitor Card — Guida Configurazione

## Configurazione minima

```yaml
type: custom:elettrodomestico-monitor-card
slot: 1
```

Questo è sufficiente per qualsiasi tipo di device (elettrodomestico, vacuum, clima, acqua, gas).

---

## Parametri disponibili

| Parametro | Tipo | Default | Descrizione |
|-----------|------|---------|-------------|
| `slot` | number | **obbligatorio** | Numero slot del device (es. `1`, `14`, `210`) |
| `name` | string | da sensore HA | Nome visualizzato nell'header. **Sovrascrive** il valore dell'entità `text.nome_elettrodomestico_xN` |
| `image_on` | string | da config flow | Path immagine stato ON (es. `/local/foto-pkg/lavatrice_on.gif`). Sovrascrive il valore salvato nel config flow |
| `image_off` | string | da config flow | Path immagine stato OFF. Sovrascrive il valore salvato nel config flow |
| `max_power` | number | `2200` | Potenza massima in W per la barra di consumo istantaneo (solo per device non-vacuum) |

---

## Comportamento automatico (nessuna configurazione necessaria)

### Immagini
Le immagini vengono caricate automaticamente dagli attributi del sensore
`sensor.time_on_elettrodomestici_xN` (configurate nel config flow HA).
Se specifichi `image_on`/`image_off` nella card, questi valori hanno **priorità**.

### Tipo di device
La card rileva automaticamente il tipo di device cercando le entità:
1. `vacuum.elettrodomestici_xN` → mostra barra batteria, click header apre controlli vacuum
2. `climate.elettrodomestici_xN` → click header apre controlli clima
3. `switch.switch_elettrodomestici_xN` → click header apre switch
4. `binary_sensor.ac_elettrodomestici_xN` → fallback

### Barra in basso
- **Vacuum**: mostra % batteria con colore (verde/arancio/rosso)
- **Tutti gli altri**: mostra consumo istantaneo in W/kW con barra proporzionale a `max_power`

---

## Esempi

### Elettrodomestico standard
```yaml
type: custom:elettrodomestico-monitor-card
slot: 1
name: Lavastoviglie
max_power: 2200
```

### Vacuum (immagini dal config flow)
```yaml
type: custom:elettrodomestico-monitor-card
slot: 210
name: Roomba
```

### Vacuum (immagini nella card)
```yaml
type: custom:elettrodomestico-monitor-card
slot: 210
name: Roomba
image_off: /local/foto-pkg/vacuum_off.gif
image_on: /local/foto-pkg/vacuum_on.gif
```

### Clima
```yaml
type: custom:elettrodomestico-monitor-card
slot: 14
name: Clima Badroom
image_off: /local/foto-pkg/fan_off.gif
image_on: /local/foto-pkg/fan_on.gif
```

### Acqua / Gas
```yaml
type: custom:elettrodomestico-monitor-card
slot: 101
name: Boiler
```

---

## Pulsanti navigazione

| Pulsante | Azione |
|----------|--------|
| ⚙️ | Popup Impostazioni (switch, soglie, orari, notifiche, reset) |
| 📊 | Popup Statistiche (cicli, consumo, costi oggi/mese/anno/ieri) |
| 🔔 | Popup Update (versione installata, notifica aggiornamenti) |
| 📈 | Popup Grafico (potenza 24h, consumo settimanale) |
| ℹ️ | Popup Info (versione, manutenzione, ultimo reset) |

### Click sull'header
Apre il `more-info` dell'entità principale del device:
- Vacuum → controlli `vacuum.elettrodomestici_xN` (start/stop/dock/locate)
- Clima → controlli `climate.elettrodomestici_xN` (temperatura, modalità)
- Standard → info `switch.switch_elettrodomestici_xN`

### Click sull'immagine
Apre popup **Ultimi 7 Giorni** con statistiche giornaliere.

---

## Risorsa Lovelace

La risorsa viene registrata automaticamente al riavvio di HA.
URL: `/elettrodomestico_monitor/elettrodomestico-monitor-card.js?v=4.43`

Se non compare, aggiungila manualmente:
**Impostazioni → Dashboard → Risorse → Aggiungi**
- URL: `/elettrodomestico_monitor/elettrodomestico-monitor-card.js`
- Tipo: Modulo JavaScript

---

## Dipendenze consigliate (HACS)

Per i popup nelle impostazioni/statistiche:
- `browser_mod` — gestione popup
- `card-mod` — styling personalizzato
- `button-card` — pulsanti avanzati
- `multiple-entity-row` — righe multi-entità
- `bar-card` — barre progress
- `mini-graph-card` — grafici
- `swipe-card` — swipe tra statistiche

