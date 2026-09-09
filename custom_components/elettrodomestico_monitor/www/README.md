# Elettrodomestico Monitor — Card JS

File: `elettrodomestico-monitor-card.js`

Dopo aver installato il custom component, aggiungi questa risorsa in Lovelace:

**Impostazioni → Dashboard → Risorse → Aggiungi risorsa**

URL: `/elettrodomestico_monitor/elettrodomestico-monitor-card.js`
Tipo: Modulo JavaScript

Configurazione card:
```yaml
type: custom:elettrodomestico-monitor-card
slot: 1
name: Lavastoviglie
image_off: /local/foto-pkg/lavastoviglie_off.png
image_on: /local/foto-pkg/lavastoviglie_on.gif
max_power: 2200
```

Per vacuum:
```yaml
type: custom:elettrodomestico-monitor-card
slot: 201
name: Roomba
image_off: /local/foto-pkg/vacuum_off.gif
image_on: /local/foto-pkg/vacuum_on.gif
vacuum: true
```
