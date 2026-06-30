# Elettrodomestico Monitor

Custom integration per Home Assistant che monitora consumi, costi e cicli di
elettrodomestici, climatizzatori, vacuum robot, impianti di irrigazione
multi-zona e dispositivi a batteria, con supporto fotovoltaico e notifiche
multi-canale.

**Versione:** 5.7.0 | **HA minima:** 2024.11 | **Repository:** github.com/Destroyer061090/elettrodomestico-monitor

---

## Cosa fa

Trasforma i sensori di potenza, portata e batteria che hai gia in casa in un
sistema unificato che misura, contabilizza e visualizza:

- consumi energetici (kWh) ed economici (EUR) per ogni dispositivo;
- separazione tra energia prelevata dalla **rete** e autoconsumo **solare**
  (fotovoltaico), con costi e risparmi distinti;
- consumo idrico reale (litri) e costo pompa per l'irrigazione;
- cicli, durate e statistiche per oggi / mese / anno e periodi precedenti;
- gestione automatica della ricarica di dispositivi a batteria entro soglie.
<img width="1553" height="860" alt="image" src="https://github.com/user-attachments/assets/320e84fa-26cb-4f37-b5ae-510d090d1d4e" />

---

## Installazione

1. Copia la cartella `elettrodomestico_monitor` in `/config/custom_components/`
2. Riavvia Home Assistant
3. Vai in **Impostazioni > Integrazioni > Aggiungi** e cerca "Elettrodomestico Monitor"
4. Configura l'Hub Globale (tariffe EUR/kWh ed EUR/m3, sensore fotovoltaico, notifiche, orari)
5. Aggiungi i device uno alla volta, oppure usa l'**Import** di una configurazione esistente

> **Dashboard in modalita YAML:** la registrazione automatica delle risorse
> Lovelace non e supportata da Home Assistant in questa modalita. Aggiungi
> manualmente le tre risorse JavaScript indicate nel log (e normale, non e un errore).

---

## Architettura in breve

| Componente | Ruolo |
|------------|-------|
| **Hub Globale** | Configurazione condivisa: tariffe, sensore FV, target notifiche, finestra oraria |
| **Appliance** | Elettrodomestici, clima, acqua, vacuum (preset dedicati) |
| **Irrigation** | Impianti multi-zona con scheduling settimanale e conteggio litri/kWh |
| **Device** | Gestione ricarica batterie con isteresi di soglia |

Ogni device ha un proprio coordinator e una propria persistenza isolata
(`instance_id` univoco). I costi rete/sole, i contatori e i cicli sono esposti
come **sensori dedicati** (non solo attributi), cosi sono cliccabili e tracciabili
nei grafici nativi di Home Assistant.

---

## Tipi di Device (Preset)

| Preset | Unita | Note |
|--------|-------|------|
| `elettrodomestico` | kWh | Generico, basato su sensore di potenza |
| `clima` | kWh | Tracciamento via entita climate |
| `acqua` | L | Volume + opzionale m3 |
| `gas` | m3 | Costo gas |
| `vacuum` | kWh | Stato e batteria del robot |
| `irrigazione` | L + kWh | Multi-zona, scheduling, pompa |
| `dispositivo` | % + cicli | Ricarica batteria con soglie start/stop |

---

## Fotovoltaico

Se abilitato nell'Hub, l'integrazione legge un sensore di potenza alla rete
(positivo = prelievo, negativo = immissione) e ripartisce l'energia di ogni
dispositivo tra **rete** e **solare** con un modello proporzionale. Espone costi
rete e risparmi solari separati, per dispositivo e per periodo.

---

## Notifiche

Canali supportati per dispositivo: **push** (mobile app), **WhatsApp**
(via `input_text`), **Alexa** e **Google** (TTS). I canali vocali rispettano la
finestra oraria configurata nell'Hub. L'invio e centralizzato in un unico modulo
(`notify_helper.py`) condiviso da tutti i coordinator.

---

## Card Lovelace

Tre custom card incluse (in `www/`):

- **elettrodomestico-monitor-card** -- card principale per appliance, clima,
  vacuum e irrigazione: stato, statistiche, impostazioni, grafici.
- **elettrodomestico-dispositivo-card** -- card dedicata ai dispositivi a batteria,
  con anello di carica e statistiche ricariche.
- **em-stat-table** -- elemento tabella stilato (Shadow DOM, immune alla
  sanitizzazione di HA) usato per tutte le statistiche; formattazione numerica
  localizzata (virgola decimale, 2 cifre).

---

## Servizi

| Servizio | Descrizione |
|----------|-------------|
| `reset_sensors` | Azzera i contatori di un device (per `entry_id`) |
| `set_maintenance` | Registra una manutenzione con data |
| `export_config` | Esporta la configurazione completa (hub + device) |
| `import_config` | Importa una configurazione |
| `irrigation_start` / `irrigation_stop` | Avvio/stop manuale ciclo irrigazione |

---

## Note tecniche

- Risorsa JS registrata con versioning (`?v=X.Y.Z`) per evitare la cache del browser.
- Dopo ogni aggiornamento, svuota la cache; per nuovi sensori puo servire un riavvio di HA.
- I grafici dei sensori nuovi si popolano nel tempo (lo storico parte dalla creazione).
- Naming entita centralizzato in `naming.py` (Python) con guard anti doppio-prefisso.
