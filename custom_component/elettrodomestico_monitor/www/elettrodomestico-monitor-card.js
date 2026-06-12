/**
 * Elettrodomestico Monitor Card v4.27
 * Card custom nativa — Shadow DOM, nessuna dipendenza da createCardElement
 * Popup via browser_mod
 *
 * Config:
 *   type: custom:elettrodomestico-monitor-card
 *   slot: 1
 *   name: Lavastoviglie
 *   image_off: /local/foto-pkg/lavatrice_off.png
 *   image_on:  /local/foto-pkg/lavatrice_on.gif
 *   max_power: 2200
 *   vacuum: false   # true → mostra barra batteria invece di potenza
 */

const DAYS_IT    = ['lunedi','martedi','mercoledi','giovedi','venerdi','sabato','domenica'];
const DAYS_LABEL = ['Lunedì','Martedì','Mercoledì','Giovedì','Venerdì','Sabato','Domenica'];

const CARD_CSS = `
* { box-sizing: border-box; margin: 0; padding: 0; }

.card {
  background: var(--ha-card-background, var(--card-background-color, #1c1c1c));
  border-radius: 16px;
  border: 2px solid rgba(0,212,255,0.35);
  box-shadow: 0 2px 12px rgba(0,0,0,0.35);
  overflow: hidden;
  font-family: var(--primary-font-family, Roboto, sans-serif);
  color: var(--primary-text-color, #e2e8f0);
}

/* Header */
.header {
  padding: 4px 16px 3px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  color: var(--secondary-text-color, #94a3b8);
  border-bottom: 1px solid rgba(128,128,128,0.12);
}

/* Main row */
.main {
  display: flex;
  align-items: stretch;
  height: 180px;
}

/* Image */
.img-col {
  flex: 0 0 40%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8px;
  cursor: pointer;
  overflow: hidden;
}
.img-col img {
  max-width: 100%;
  max-height: 164px;
  object-fit: contain;
}
.img-icon {
  font-size: 64px;
  cursor: pointer;
  user-select: none;
}

/* Info rows */
.info-col {
  flex: 0 0 60%;
  display: flex;
  flex-direction: column;
  justify-content: space-around;
  padding: 4px 4px 4px 0;
}
.info-row {
  display: flex;
  align-items: center;
  gap: 0;
  height: 40px;
  cursor: pointer;
  border-radius: 6px;
  padding: 2px 4px;
  transition: background 0.15s;
}
.info-row:hover { background: rgba(128,128,128,0.08); }
.info-ico {
  width: 40px;
  text-align: center;
  font-size: 18px;
  flex-shrink: 0;
}
.info-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.info-lbl {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  color: var(--secondary-text-color, #94a3b8);
  line-height: 1.2;
}
.info-val {
  font-size: 12px;
  font-weight: 500;
  color: var(--primary-text-color, #e2e8f0);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.3;
}

/* Bar */
.bar-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 12px 2px;
  background: rgba(0,0,0,0.04);
}
.bar-ico { font-size: 15px; flex-shrink: 0; }
.bar-lbl { font-size: 11px; color: var(--secondary-text-color, #94a3b8); flex: 1; }
.bar-val { font-size: 13px; font-weight: 700; }
.bar-track {
  height: 4px;
  background: rgba(128,128,128,0.15);
  border-radius: 2px;
  margin: 0 12px 4px;
}
.bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.4s ease, background-color 0.3s;
}

/* Nav */
.nav {
  display: flex;
  border-top: 1px solid rgba(128,128,128,0.12);
}
.nav-btn {
  flex: 1;
  border: none;
  background: none;
  padding: 10px 4px;
  cursor: pointer;
  font-size: 18px;
  color: var(--secondary-text-color, #94a3b8);
  transition: color 0.15s, background 0.15s;
  line-height: 1;
}
.nav-btn:hover {
  color: var(--primary-text-color, #e2e8f0);
  background: rgba(128,128,128,0.08);
}
`;

class ElettrodomesticoMonitorCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config  = null;
    this._hass    = null;
    this._slot    = null;
    this._ready   = false;
  }

  static getStubConfig() {
    return { slot: 1, name: 'Elettrodomestico', max_power: 2200 };
  }

  setConfig(cfg) {
    if (!cfg.slot) throw new Error('"slot" è obbligatorio');
    this._config  = { max_power: 2200, vacuum: false, clima: false, ...cfg };
    this._slot    = `x${cfg.slot}`;
    this._isVac   = !!cfg.vacuum;
    this._isClima = !!cfg.clima;
    this._ready   = false;
    this._build();
  }

  set hass(h) {
    this._hass = h;
    if (!this._ready) this._build();
    else this._update();
  }

  // ── Helpers ─────────────────────────────────────────────────────────────────

  _s(eid, def = '')    { return this._hass?.states[eid]?.state ?? def; }
  _a(eid, attr, def = '') { return this._hass?.states[eid]?.attributes?.[attr] ?? def; }
  _sf(eid, def = 0)   { return parseFloat(this._s(eid, String(def))) || def; }
  _q(sel)             { return this.shadowRoot.querySelector(sel); }
  _eid(sfx)           { return `sensor.${sfx}_${this._slot}`; }

  // ── Build DOM ────────────────────────────────────────────────────────────────

  _build() {
    if (!this._config || !this._hass) return;
    this._ready = true;

    const r = this.shadowRoot;
    r.innerHTML = '';

    const style = document.createElement('style');
    style.textContent = CARD_CSS;
    r.appendChild(style);

    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = `
      <div class="header" style="display:flex;align-items:center;gap:6px;">
          <span id="hdr" style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${this._config.name || 'Elettrodomestico'}</span>
          <span id="online-dot" style="width:9px;height:9px;border-radius:50%;background:#94a3b8;flex-shrink:0;display:inline-block;margin-right:4px" title=""></span>
        </div>

      <div class="main">
        <div class="img-col" id="img-wrap">
          <span class="img-icon" id="img-icon">🔌</span>
          <img id="img-el" style="display:none" src="" alt="">
        </div>

        <div class="info-col">
          <div class="info-row" id="ir0">
            <span class="info-ico">⏻</span>
            <div class="info-text">
              <span class="info-lbl" id="lbl0">Ultimo Avvio</span>
              <span class="info-val" id="val0">—</span>
            </div>
          </div>
          <div class="info-row" id="ir1">
            <span class="info-ico">🕐</span>
            <div class="info-text">
              <span class="info-lbl" id="lbl1">Durata Ultimo</span>
              <span class="info-val" id="val1">—</span>
            </div>
          </div>
          <div class="info-row" id="ir2">
            <span class="info-ico">📊</span>
            <div class="info-text">
              <span class="info-lbl" id="lbl2">Consumo Ultimo</span>
              <span class="info-val" id="val2">—</span>
            </div>
          </div>
          <div class="info-row" id="ir3">
            <span class="info-ico">€</span>
            <div class="info-text">
              <span class="info-lbl" id="lbl3">Costo Ultimo</span>
              <span class="info-val" id="val3">—</span>
            </div>
          </div>
        </div>
      </div>

      <div class="bar-row">
        <span class="bar-ico" id="bico">${this._isVac ? '🔋' : '⚡'}</span>
        <span class="bar-lbl">${this._isVac ? 'Batteria' : 'Consumo Istantaneo'}</span>
        <span class="bar-val" id="bval">—</span>
      </div>
      <div class="bar-track">
        <div class="bar-fill" id="bfill" style="width:0%;background:#94a3b8"></div>
      </div>

      <div id="irr-countdown" style="display:none; padding:4px 12px; font-size:0.85em; color:var(--secondary-text-color); text-align:center;">
        ⏱ <span id="irr-zone-name">—</span> &nbsp;|&nbsp; <span id="irr-countdown-val">0:00</span>
      </div>

      <div class="nav">
        <button class="nav-btn" id="bn0" title="Impostazioni">⚙️</button>
        <button class="nav-btn" id="bn1" title="Statistiche">📊</button>
        <button class="nav-btn" id="bn2" title="Update">🔔</button>
        <button class="nav-btn" id="bn3" title="Grafico">📈</button>
        <button class="nav-btn" id="bn4" title="Info">ℹ️</button>
      </div>
    `;
    r.appendChild(card);
    this._wire();
    this._update();
  }

  // ── Update ───────────────────────────────────────────────────────────────────

  _update() {
    if (!this._ready || !this._hass) return;
    const s = this._slot;

    // ── Detect device type (robust multi-sensor check) ──────────────────
    const irrMastId = `sensor.irrigazione_time_on_${s}`;
    const _isIrr = (
      this._hass.states[`sensor.irrigazione_time_on_${s}`]   !== undefined ||
      this._hass.states[`sensor.irrigazione_portata_${s}`]   !== undefined ||
      this._hass.states[`sensor.irrigazione_pompa_w_${s}`]   !== undefined
    );

    const mastId = _isIrr
      ? irrMastId
      : `sensor.time_on_elettrodomestici_${s}`;
    const acId   = _isIrr
      ? irrMastId   // use irrigazione master for "is active" check
      : `binary_sensor.ac_elettrodomestici_${s}`;
    const pwId   = _isIrr
      ? `sensor.irrigazione_portata_${s}`
      : `sensor.potenza_elettrodomestici_w_${s}`;
    const pw2Id  = _isIrr
      ? `sensor.irrigazione_pompa_w_${s}`
      : null;
    const batId   = `sensor.batteria_vacuum_${s}`;
    const nmId    = `text.nome_elettrodomestico_${s}`;
    const ma      = this._hass.states[mastId]?.attributes || {};
    const isOn    = _isIrr
      ? (ma.ciclo_attivo === true)
      : this._s(acId) === 'on';
    // Irrigation countdown display
    const cdRow = this._q('#irr-countdown');
    if (cdRow) {
      if (_isIrr && isOn) {
        const irrA = this._hass.states[`sensor.irrigazione_time_on_${s}`]?.attributes || {};
        const cdSecs = irrA.countdown_s || 0;
        const cdZone = irrA.zona_attiva || '—';
        const cdMins = Math.floor(cdSecs / 60);
        const cdSecR = cdSecs % 60;
        const cdStr  = `${cdMins}:${String(cdSecR).padStart(2,'0')}`;
        cdRow.style.display = '';
        const zn = this._q('#irr-zone-name');
        const cv = this._q('#irr-countdown-val');
        if (zn) zn.textContent = cdZone;
        if (cv) cv.textContent = cdStr;
      } else {
        cdRow.style.display = 'none';
      }
    }
    const pwW     = this._sf(pwId, 0);
    const pw2W    = pw2Id ? this._sf(pw2Id, 0) : 0;
    const batPct  = this._sf(batId, 0);  // kept for compatibility

    // Header — config name, then text entity (irr: nome_irrigazione, else: nome_elettrodomestico)
    const irrNmId = `text.nome_irrigazione_${s}`;
    const nm = this._config.name
      || (_isIrr ? (this._s(irrNmId, '') || ma.appliance_name || '') : this._s(nmId, ''))
      || 'Elettrodomestico';
    this._q('#hdr').textContent = `Centro Controllo ${nm}`;
    // Online/offline dot
    // Priority: trigger_entity (vacuum/clima real device) > switch_state > sensor_online (power sensor)
    const _trigEid   = _isIrr
      ? `sensor.irrigazione_portata_${s}`
      : (ma.trigger_entity || '');
    const _trigSt    = _trigEid ? this._hass.states[_trigEid] : undefined;
    let _isOnline;
    if (_isIrr) {
      // Irrigation: online if portata sensor exists
      _isOnline = _trigSt !== undefined;
    } else if (_trigSt !== undefined) {
      // Vacuum/clima: check real device entity availability
      const _ts = _trigSt.state ?? 'unavailable';
      _isOnline = _ts !== 'unavailable' && _ts !== 'unknown';
    } else if (ma.switch_state !== undefined && ma.switch_state !== null) {
      // Switch-based device: online if switch entity is not unavailable
      _isOnline = ma.switch_state !== 'unavailable' && ma.switch_state !== 'unknown';
    } else {
      // Power-sensor only device: use coordinator sensor_online flag
      _isOnline = ma.sensor_online !== false;
    }
    const _dot = this._q('#online-dot');
    if (_dot) {
      _dot.style.background = _isOnline ? '#22c55e' : '#ef4444';
      _dot.title = _isOnline ? 'Online' : 'Offline';
    }

    // Image: prefer config values, fallback to sensor attributes
    const imgOff = this._config.image_off || ma.image_off || '';
    const imgOn  = this._config.image_on  || ma.image_on  || imgOff;
    const imgEl  = this._q('#img-el');
    const ico    = this._q('#img-icon');
    const src    = (isOn && imgOn) ? imgOn : imgOff;
    if (src) {
      ico.style.display = 'none';
      imgEl.style.display = '';
      if (imgEl.src !== src) imgEl.src = src;
    } else {
      ico.style.display = '';
      imgEl.style.display = 'none';
    }

    // 4 info rows
    let term, dur, cons, cost;
    if (_isIrr) {
      // Read from irrigation master sensor attributes
      const irrAttr = this._hass.states[`sensor.irrigazione_time_on_${s}`]?.attributes || {};
      term = irrAttr.zona_attiva || (isOn ? 'Irrigazione attiva' : '—');
      dur  = irrAttr.tempo_oggi || '—';
      cons = irrAttr.litri_oggi !== undefined ? `${irrAttr.litri_oggi} L` : '—';
      cost = irrAttr.costo_acqua_oggi !== undefined ? irrAttr.costo_acqua_oggi : undefined;
    } else {
      term = ma.terminato ?? '—';
      dur  = ma.tempo_ciclo_elettrodomestici ?? ma.tempo_ciclo_vacuum ?? '—';
      cons = ma.consumo_ciclo_elettrodomestici ?? '—';
      cost = ma.costo_ciclo_elettrodomestici;
    }
    this._q('#lbl0').textContent = isOn ? (_isIrr ? 'Zona Attiva' : 'Stato')         : (_isIrr ? 'Zona Ultima' : 'Ultimo Avvio');
    this._q('#val0').textContent = term;
    this._q('#lbl1').textContent = isOn ? 'Tempo Oggi'   : 'Tempo Oggi';
    this._q('#val1').textContent = dur;
    this._q('#lbl2').textContent = _isIrr ? 'Litri Oggi' : (isOn ? 'Consumo ON' : 'Consumo Ultimo');
    this._q('#val2').textContent = _isIrr ? String(cons) : (typeof cons === 'number' ? `${cons} kWh` : String(cons));
    this._q('#lbl3').textContent = _isIrr ? '€ Acqua' : (isOn ? 'Costo Attuale' : 'Costo Ultimo');
    this._q('#val3').textContent = _isIrr
      ? (pw2W > 0 ? `${pw2W.toFixed(0)} W` : '—')
      : ((cost !== undefined && cost !== null && cost !== '') ? `${cost} €` : '—');

    // Bar — irrigation: show L/min; vacuum: battery; else: power
    const batRaw  = this._sf(batId, -1);
    const isVacAuto = !_isIrr && (batRaw >= 0 || this._hass?.states[`vacuum.elettrodomestici_${s}`] !== undefined);
    if (_isIrr) {
      // Irrigation bar 1: L/min portata
      const maxFlow = this._config.max_flow || 30;
      const pct = Math.min(100, Math.max(0, (pwW / maxFlow) * 100));
      const col = pwW > 0 ? '#3b82f6' : '#94a3b8';
      this._q('#bico').textContent = '💧';
      const barLbl = this._q('.bar-lbl');
      if (barLbl) barLbl.textContent = 'Portata';
      this._q('#bval').textContent = `${pwW.toFixed(1)} L/min`;
      this._q('#bfill').style.width = `${pct}%`;
      this._q('#bfill').style.background = col;

      // Irrigation bar 2: pump W — shown only if sensor exists
      const hasPump = this._hass?.states[`sensor.irrigazione_pompa_w_${s}`] !== undefined;
      let bar2 = this._q('#bar2-row');
      if (hasPump) {
        const maxPow = this._config.max_pump_power || 3000;
        const pct2 = Math.min(100, Math.max(0, (pw2W / maxPow) * 100));
        const col2 = pw2W > 0 ? '#f59e0b' : '#94a3b8';
        if (!bar2) {
          const track = this._q('.bar-track');
          if (track) {
            const row = document.createElement('div');
            row.id = 'bar2-row';
            row.className = 'bar-row';
            row.style.marginTop = '4px';
            row.innerHTML = `<span class="bar-ico">⚡</span><span class="bar-lbl">Pompa</span><span class="bar-val" id="bval2">—</span>`;
            const track2 = document.createElement('div');
            track2.id = 'bar2-track';
            track2.className = 'bar-track';
            track2.innerHTML = `<div class="bar-fill" id="bfill2" style="width:0%;background:#94a3b8"></div>`;
            track.after(track2); track.after(row);
            bar2 = row;
            row.addEventListener('click', () => this._moreInfo(`sensor.irrigazione_pompa_w_${s}`));
            track2.addEventListener('click', () => this._moreInfo(`sensor.irrigazione_pompa_w_${s}`));
          }
        }
        const bval2 = this._q('#bval2');
        const bfill2 = this._q('#bfill2');
        if (bval2) bval2.textContent = `${pw2W.toFixed(0)} W`;
        if (bfill2) { bfill2.style.width = `${pct2}%`; bfill2.style.background = col2; }
      } else if (bar2) {
        bar2.remove();
        const t2 = this._q('#bar2-track');
        if (t2) t2.remove();
      }
    } else if (isVacAuto) {
      const pct = Math.min(100, Math.max(0, batRaw >= 0 ? batRaw : batPct));
      const clr = pct > 50 ? '#22c55e' : pct > 20 ? '#f97316' : '#ef4444';
      this._q('#bval').textContent = `${pct}%`;
      this._q('#bval').style.color = clr;
      this._q('#bico').style.color = clr;
      this._q('#bfill').style.width = `${pct}%`;
      this._q('#bfill').style.backgroundColor = clr;
    } else {
      const max = this._config.max_power || 2200;
      const pct = Math.min(100, (pwW / max) * 100);
      const clr = pwW > max * 0.8 ? '#ef4444' : pwW > 10 ? '#1e90ff' : '#94a3b8';
      const txt = pwW >= 1000 ? `${(pwW/1000).toFixed(2)} kW` : `${pwW.toFixed(0)} W`;
      this._q('#bval').textContent = txt;
      this._q('#bval').style.color = clr;
      this._q('#bico').style.color = clr;
      this._q('#bfill').style.width = `${pct}%`;
      this._q('#bfill').style.backgroundColor = clr;
    }
  }

  // ── Popup ────────────────────────────────────────────────────────────────────

  _popup(title, content) {
    this.dispatchEvent(new CustomEvent('ll-custom', {
      bubbles: true, composed: true,
      detail: {
        action: 'fire-dom-event',
        browser_mod: {
          service: 'browser_mod.popup',
          data: {
            title,
            style: '--popup-background-color: var(--card-background-color); --dialog-backdrop-filter: blur(2em) brightness(0.75);',
            content,
          },
        },
      },
    }));
  }

  _moreInfo(eid) {
    this.dispatchEvent(new CustomEvent('hass-more-info', {
      bubbles: true, composed: true, detail: { entityId: eid },
    }));
  }

  // ── Wire ─────────────────────────────────────────────────────────────────────

  _wire() {
    const s = this._slot;
    const _isIrr = (
      this._hass?.states[`sensor.irrigazione_time_on_${s}`]   !== undefined ||
      this._hass?.states[`sensor.irrigazione_portata_${s}`]   !== undefined ||
      this._hass?.states[`sensor.irrigazione_pompa_w_${s}`]   !== undefined
    );
    const cm = () => ({
      style: `ha-card { background: var(--card-background-color) !important; }
              .entities-row, .info, hui-generic-entity-row, state-badge + div {
                color: var(--primary-text-color) !important;
              }
              .secondary { color: var(--secondary-text-color) !important; }`
    });

    // Header → more-info: auto-detect best entity for this device
    this._q('#hdr').style.cursor = 'pointer';
    this._q('#hdr').addEventListener('click', () => {
      // Priority: vacuum → climate → switch → binary_sensor
      const ents = [
        `vacuum.elettrodomestici_${s}`,
        `climate.elettrodomestici_${s}`,
        `switch.switch_elettrodomestici_${s}`,
        `binary_sensor.ac_elettrodomestici_${s}`,
      ];
      const found = ents.find(e => this._hass?.states[e] !== undefined);
      if (found) this._moreInfo(found);
    });

    // Image → 7 giorni
    this._q('#img-wrap').addEventListener('click', () => {
      this._popup('Ultimi 7 Giorni', {
        type: 'entities', card_mod: cm(),
        entities: [
          { type: 'divider' },
          ...DAYS_IT.flatMap((d, i) => ([
            {
              entity: `sensor.settimana_${d}_elettrodomestici_${s}`,
              name: DAYS_LABEL[i],
              type: 'custom:multiple-entity-row',
              state_header: _isIrr ? 'L' : 'kWh',
              state_color: false, icon: 'mdi:calendar',
              entities: _isIrr ? [
                { attribute: 'cicli', name: 'CICLI' },
                { attribute: 'tempo', name: 'TEMPO' },
                { attribute: 'kwh', name: 'kWh' },
              ] : [
                { attribute: 'cicli', name: 'CICLI' },
                { attribute: 'tempo', name: 'TEMPO' },
                { attribute: 'costo_eur', name: 'EURO', unit: '€' },
              ],
            },
            { type: 'divider' },
          ])),
        ],
      });
    });

    // Info rows → more-info
    const _ir0Target = _isIrr ? `sensor.irrigazione_time_on_${s}` : `sensor.time_on_elettrodomestici_${s}`;
    this._q('#ir0').addEventListener('click', () => this._moreInfo(_ir0Target));
    const _ir1Target = _isIrr ? `sensor.irrigazione_litri_oggi_${s}` : `sensor.ultimo_ciclo_elettrodomestici_${s}`;
    this._q('#ir1').addEventListener('click', () => this._moreInfo(_ir1Target));
    const _ir2Target = _isIrr ? `sensor.irrigazione_kwh_oggi_${s}` : `sensor.ultimo_ciclo_elettrodomestici_${s}`;
    this._q('#ir2').addEventListener('click', () => this._moreInfo(_ir2Target));
    const _ir3Target = _isIrr ? `sensor.irrigazione_time_on_${s}` : `sensor.costo_oggi_elettrodomestici_${s}`;
    this._q('#ir3').addEventListener('click', () => this._moreInfo(_ir3Target));

    // Bar click → HA native more-info (irrigation: portata sensor; others: power/battery)
    const _barClick = () => {
      const irrSensor = `sensor.irrigazione_portata_${s}`;
      const batSensor = `sensor.batteria_vacuum_${s}`;
      const pwrSensor = `sensor.potenza_elettrodomestici_w_${s}`;
      const isIrr = this._hass?.states[irrSensor] !== undefined;
      const hasBat = this._hass?.states[batSensor] !== undefined;
      this._moreInfo(isIrr ? irrSensor : (hasBat ? batSensor : pwrSensor));
    };
    this._q('.bar-row').addEventListener('click', _barClick);
    this._q('.bar-track').addEventListener('click', _barClick);

    // Nav buttons
    this._q('#bn0').addEventListener('click', () => this._showSettings());
    this._q('#bn1').addEventListener('click', () => this._showStats());
    this._q('#bn2').addEventListener('click', () => this._showUpdate());
    this._q('#bn3').addEventListener('click', () => this._showGraph());
    this._q('#bn4').addEventListener('click', () => this._showInfo());
  }

  // ── Popup contents ───────────────────────────────────────────────────────────

  _cm() {
    return {
      style: `ha-card { background: var(--card-background-color) !important; }
              .entities-row, .info, hui-generic-entity-row, state-badge + div {
                color: var(--primary-text-color) !important;
              }
              .secondary { color: var(--secondary-text-color) !important; }`
    };
  }

  _showIrrSettings(s) {
    const DAYS_IT    = ['lunedi','martedi','mercoledi','giovedi','venerdi','sabato','domenica'];
    const DAYS_LABEL = ['Lun','Mar','Mer','Gio','Ven','Sab','Dom'];

    const zoneSwitches = Object.keys(this._hass.states)
      .filter(e => e.startsWith(`switch.irrigazione_z`) && e.endsWith(`_${s}`))
      .sort();

    // Build zone rows: switch + duration number paired
    const zoneRows = zoneSwitches.flatMap(sw => {
      const zMatch = sw.match(/irrigazione_z(\d+)_x/);
      if (!zMatch) return [{ entity: sw, icon: 'mdi:water' }];
      const zNum  = zMatch[1];
      const numEid = `number.irrigazione_z${zNum}_durata_${s}`;
      const hasNum = !!this._hass.states[numEid];
      if (hasNum) {
        // Paired row: switch left, duration number as secondary entity
        return [{
          entity: sw,
          name: `Zona ${zNum}`,
          icon: 'mdi:water',
          type: 'custom:multiple-entity-row',
          entities: [{ entity: numEid, name: 'min' }],
        }];
      }
      return [{ entity: sw, icon: 'mdi:water' }];
    });

    const entities = [
      { type: 'divider' },
      { entity: `switch.irrigazione_master_${s}`,         name: '▶ Avvia Manualmente Ciclo', icon: 'mdi:sprinkler-variant' },
      { entity: `switch.irrigazione_programmazione_${s}`, name: 'Programmazione Automatica',  icon: 'mdi:calendar-clock' },
      { type: 'divider' },
      { type: 'section', label: 'Orari Programmazione' },
      { entity: `time.irrigazione_s1_orario_${s}`, name: 'Orario 1', icon: 'mdi:clock-start' },
      { entity: `time.irrigazione_s2_orario_${s}`, name: 'Orario 2', icon: 'mdi:clock-start' },
      { entity: `time.irrigazione_s3_orario_${s}`, name: 'Orario 3', icon: 'mdi:clock-start' },
      { type: 'divider' },
      { type: 'section', label: 'Giorni Attivi' },
      ...DAYS_IT.map((d, i) => ({
        entity: `switch.irrigazione_${d}_${s}`, name: DAYS_LABEL[i], icon: 'mdi:calendar-week',
      })),
      { type: 'divider' },
      { type: 'section', label: 'Zone — Switch e Durata (min)' },
      ...zoneRows,
      { type: 'divider' },
    ];

    this._popup('Irrigazione', { type: 'entities', card_mod: this._cm(), entities });
  }

    _showSettings() {
    const s = this._slot;
    const irrMastId = `sensor.irrigazione_time_on_${s}`;
    const _isIrr = (
      this._hass?.states[`sensor.irrigazione_time_on_${s}`]   !== undefined ||
      this._hass?.states[`sensor.irrigazione_portata_${s}`]   !== undefined ||
      this._hass?.states[`sensor.irrigazione_pompa_w_${s}`]   !== undefined
    );

    if (_isIrr) {
      // ── Irrigation settings popup ────────────────────────────────────────
      const DAYS_IT = ['lunedi','martedi','mercoledi','giovedi','venerdi','sabato','domenica'];
      const DAYS_LABEL = ['Lun','Mar','Mer','Gio','Ven','Sab','Dom'];
      this._popup('Impostazioni Irrigazione', {
        type: 'entities', card_mod: this._cm(),
        entities: [
          { type: 'divider' },
          { entity: `switch.irrigazione_master_${s}`, name: '▶ Avvia Manualmente Ciclo', icon: 'mdi:sprinkler-variant' },
          { type: 'divider' },
          { type: 'section', label: 'Programmazione Orari' },
          { entity: `time.irrigazione_s1_orario_${s}`, name: 'Orario 1', icon: 'mdi:clock-start' },
          { entity: `time.irrigazione_s2_orario_${s}`, name: 'Orario 2', icon: 'mdi:clock-start' },
          { entity: `time.irrigazione_s3_orario_${s}`, name: 'Orario 3', icon: 'mdi:clock-start' },
          { type: 'divider' },
          { type: 'section', label: 'Giorni Attivi' },
          ...DAYS_IT.map((d, i) => ({
            entity: `switch.irrigazione_${d}_${s}`, name: DAYS_LABEL[i], icon: 'mdi:calendar-week',
          })),
          { type: 'divider' },
          { entity: `switch.irrigazione_programmazione_${s}`, name: '📅 Programmazione Automatica', icon: 'mdi:calendar-clock' },
          { type: 'divider' },
          { type: 'section', label: 'Zone — Durata e Controllo Manuale' },
          ...(Object.keys(this._hass.states)
            .filter(e => e.startsWith(`switch.irrigazione_z`) && e.endsWith(`_${s}`))
            .sort()
            .map(sw => ({ entity: sw, icon: 'mdi:water' }))),
          { type: 'divider' },
        ],
      });
      return;
    }

    // ── Standard appliance settings popup ───────────────────────────────────
    this._popup('Impostazioni', {
      type: 'entities', card_mod: this._cm(),
      entities: [
        { type: 'divider' },
        { entity: 'sensor.time', name: 'Orologio', icon: 'mdi:clock-outline' },
        { type: 'divider' },
        {
          entity: `sensor.programma_elettrodomestici_${s}`,
          name: 'Fascia Oraria Notifiche', icon: 'mdi:timer-outline',
          type: 'custom:multiple-entity-row', state_header: 'SPEGNIMENTO',
          entities: [{ entity: `sensor.programma_elettrodomestici_${s}`, attribute: 'accensione', name: 'ACCENSIONE' }],
        },
        { type: 'divider' },
        { entity: `switch.notifica_push_elettrodomestici_${s}`, name: 'Push', icon: 'mdi:cellphone' },
        { entity: `switch.notifica_alexa_elettrodomestici_${s}`, name: 'Alexa', icon: 'mdi:amazon-alexa' },
        { entity: `switch.notifica_google_elettrodomestici_${s}`, name: 'Google', icon: 'mdi:google-home' },
        { entity: `switch.notifica_whatsapp_elettrodomestici_${s}`, name: 'WhatsApp', icon: 'mdi:whatsapp' },
        { type: 'divider' },
        { entity: `binary_sensor.ac_elettrodomestici_${s}`, name: 'Stato Ciclo', icon: 'mdi:state-machine' },
        { entity: `text.messaggio_elettrodomestico_${s}`, name: 'Messaggio', icon: 'mdi:message-text' },
        { type: 'divider' },
        {
          entity: `sensor.time_on_elettrodomestici_${s}`,
          name: 'Soglia / Ritardi', icon: 'mdi:flash',
          type: 'custom:multiple-entity-row', state_header: 'W',
          entities: [
            { entity: `number.soglia_lavoro_elettrodomestici_w_${s}`, name: 'SOGLIA' },
            { entity: `number.tempo_innesco_elettrodomestici_m_${s}`, name: 'RITARDO OFF' },
            { entity: `number.avvio_ritardato_elettrodomestici_s_${s}`, name: 'RITARDO ON' },
          ],
        },
        { type: 'divider' },
        { entity: `time.orario_accensione_elettrodomestici_${s}`, name: 'Auto ON', icon: 'mdi:clock-start' },
        { entity: `time.orario_spegnimento_elettrodomestici_${s}`, name: 'Auto OFF', icon: 'mdi:clock-end' },
        { type: 'divider' },
        { entity: `button.reset_contatori_elettrodomestici_${s}`, name: 'Reset Contatori', icon: 'mdi:restore' },
        { type: 'divider' },
        { entity: `sensor.costo_energia_elettrodomestici_${s}`, name: 'Costo Energia', icon: 'mdi:currency-eur' },
        { type: 'divider' },
      ],
    });
  }

  _showIrrStats(s) {
    const scm = { style: 'ha-card { border-width:0px !important; background:none !important; } .entities-row,.info { color:var(--primary-text-color)!important; }' };
    const mid = `sensor.irrigazione_time_on_${s}`;

    // Row: litri | kWh | € acqua | € pompa — all from master sensor attributes
    const iRow = (lAttr, kAttr, cAcquaAttr, cKwhAttr, icon, label) => ({
      type: 'custom:multiple-entity-row',
      entity: mid,
      name: label, icon, state_color: false,
      state_header: 'L',
      entities: [
        { attribute: lAttr,      name: 'L' },
        { attribute: kAttr,      name: 'kWh' },
        { attribute: cAcquaAttr, name: '€ Acqua', unit: '€' },
        { attribute: cKwhAttr,   name: '€ Pompa', unit: '€' },
      ],
    });

    this._popup('Statistiche Irrigazione', {
      type: 'entities', card_mod: this._cm(), show_header_toggle: false,
      entities: [
        { type: 'section', label: 'Stato Attuale' },
        { entity: mid, attribute: 'zona_attiva', name: 'Zona Attiva',  icon: 'mdi:water' },
        { entity: mid, attribute: 'tempo_oggi',  name: 'Tempo Oggi',   icon: 'mdi:clock-outline' },
        { entity: mid, attribute: 'countdown_s', name: 'Countdown (s)',icon: 'mdi:timer' },
        { type: 'divider' },
        { type: 'section', label: 'Consumi e Costi' },
        { type: 'custom:hui-element', card_type: 'vertical-stack', cards: [{ type: 'vertical-stack', cards: [
          { type: 'custom:swipe-card', start_card: 0,
            parameters: { roundLengths:true, effect:'coverflow', speed:650, spaceBetween:20, threshold:7, coverflowEffect:{rotate:80,depth:300} },
            cards: [
              { type: 'entities', card_mod: scm, entities: [
                { type: 'section', label: 'Oggi' },
                iRow('litri_oggi',  'kwh_oggi',  'costo_acqua_oggi', 'costo_kwh_oggi',  'mdi:calendar',             'Oggi'),
                { type: 'section', label: 'Mese' },
                iRow('litri_mese',  'kwh_mese',  'costo_acqua_mese', 'costo_kwh_mese',  'mdi:calendar-week-begin',  'Mese'),
                { type: 'section', label: 'Anno' },
                iRow('litri_anno',  'kwh_anno',  'costo_acqua_anno', 'costo_kwh_anno',  'mdi:calendar-month',       'Anno'),
              ]},
            ],
          },
        ]}] },
      ],
    });
  }

    _showStats() {
    const s = this._slot;
    const _isIrr = (
      this._hass.states[`sensor.irrigazione_time_on_${s}`]   !== undefined ||
      this._hass.states[`sensor.irrigazione_portata_${s}`]   !== undefined
    );

    if (_isIrr) {
      this._showIrrStats(s);
      return;
    }

    // ── Standard appliance stats ──────────────────────────────────────────
    const scm = { style: 'ha-card { border-width:0px !important; background:none !important; } .entities-row,.info { color:var(--primary-text-color)!important; }' };
    const mid = `sensor.time_on_elettrodomestici_${s}`;
    const mRow = (attr, icon, ents) => ({
      entity: mid,
      attribute: attr, unit: '€', name: false,
      state_header: 'EURO', icon, state_color: true,
      type: 'custom:multiple-entity-row', entities: ents,
    });
    const pE = (cid, ta, eid) => [
      { entity: cid, name: 'CICLI' },
      { entity: mid, attribute: ta, name: 'TEMPO' },
      { entity: eid, name: 'CONSUMO' },
    ];

    this._popup('Statistiche', {
      type: 'entities', card_mod: this._cm(), show_header_toggle: false,
      entities: [
        { type: 'section', label: 'Elettrodomestico' },
        { type: 'custom:hui-element', card_type: 'vertical-stack', cards: [{ type: 'vertical-stack', cards: [
          mRow('costo_ciclo_elettrodomestici', 'mdi:power-plug', [
            { entity: mid, attribute: 'terminato', name: 'STATO' },
            { entity: mid, attribute: 'tempo_ciclo_elettrodomestici', name: 'TEMPO' },
            { entity: mid, attribute: 'consumo_ciclo_elettrodomestici', name: 'CONSUMO' },
          ]),
          { type: 'custom:swipe-card', start_card: 0,
            parameters: { roundLengths:true, effect:'coverflow', speed:650, spaceBetween:20, threshold:7, coverflowEffect:{rotate:80,depth:300} },
            cards: [
              { type: 'entities', card_mod: scm, entities: [
                { type: 'section', label: 'Oggi' },
                mRow('costo_consumo_giornaliero_elettrodomestici','mdi:calendar', pE(`sensor.cicli_oggi_elettrodomestici_${s}`,'Oggi',`sensor.energy_oggi_elettrodomestici_${s}`)),
                { type: 'section', label: 'Mese' },
                mRow('costo_consumo_mensile_elettrodomestici','mdi:calendar-week-begin', pE(`sensor.cicli_mese_elettrodomestici_${s}`,'Mese',`sensor.energy_mese_elettrodomestici_${s}`)),
                { type: 'section', label: 'Anno' },
                mRow('costo_consumo_annuale_elettrodomestici','mdi:calendar-month', pE(`sensor.cicli_anno_elettrodomestici_${s}`,'Anno',`sensor.energy_anno_elettrodomestici_${s}`)),
              ]},
              { type: 'entities', card_mod: scm, entities: [
                { type: 'section', label: 'Ieri' },
                mRow('costo_consumo_ieri_elettrodomestici','mdi:calendar',[
                  { entity:`sensor.cicli_oggi_elettrodomestici_${s}`, attribute:'last_period', name:'CICLI' },
                  { entity: mid, attribute:'Ieri', name:'TEMPO' },
                  { entity:`sensor.energy_oggi_elettrodomestici_${s}`, attribute:'last_period', unit:'kWh', name:'CONSUMO' },
                ]),
                { type: 'section', label: 'Mese Precedente' },
                mRow('costo_consumo_mese_precedente_elettrodomestici','mdi:calendar-week-begin',[
                  { entity:`sensor.cicli_mese_elettrodomestici_${s}`, attribute:'last_period', name:'CICLI' },
                  { entity: mid, attribute:'Mese Precedente', name:'TEMPO' },
                  { entity:`sensor.energy_mese_elettrodomestici_${s}`, attribute:'last_period', unit:'kWh', name:'CONSUMO' },
                ]),
                { type: 'section', label: 'Anno Precedente' },
                mRow('costo_consumo_anno_precedente_elettrodomestici','mdi:calendar-month',[
                  { entity:`sensor.cicli_anno_elettrodomestici_${s}`, attribute:'last_period', name:'CICLI' },
                  { entity: mid, attribute:'Anno Precedente', name:'TEMPO' },
                  { entity:`sensor.energy_anno_elettrodomestici_${s}`, attribute:'last_period', unit:'kWh', name:'CONSUMO' },
                ]),
              ]},
            ],
          },
        ]}] },
      ],
    });
  }

  _showUpdate() {
    const s = this._slot;
    const _isIrr = (
      this._hass.states[`sensor.irrigazione_time_on_${s}`]   !== undefined ||
      this._hass.states[`sensor.irrigazione_portata_${s}`]   !== undefined
    );
    // Unified update popup — same for all device types
    const verEid = _isIrr
      ? 'sensor.aggiornamento_elettrodomestici_hub'
      : `sensor.versione_elettrodomestici_${s}`;
    this._popup('Update', {
      type: 'entities', card_mod: this._cm(),
      entities: [
        { type: 'divider' },
        { entity: `switch.notifica_update_elettrodomestici_${s}`,
          name: 'Notifica Push Update', icon: 'mdi:bell-ring', state_color: true },
        { type: 'divider' },
        {
          entity: 'sensor.aggiornamento_elettrodomestici_hub',
          attribute: 'versione_disponibile', name: 'Versione', icon: 'mdi:update',
          type: 'custom:multiple-entity-row',
          entities: [{ entity: verEid, name: 'INSTALLATA' }],
        },
        { type: 'divider' },
      ],
    });
  }

  _showGraph() {
    const s = this._slot;
    const gcm = { style: 'ha-card { color:var(--primary-text-color)!important; background:var(--card-background-color)!important; }' };
    const _isIrr = (
      this._hass.states[`sensor.irrigazione_time_on_${s}`]   !== undefined ||
      this._hass.states[`sensor.irrigazione_portata_${s}`]   !== undefined
    );

    if (_isIrr) {
      const irrCards = [
        {
          type: 'custom:mini-graph-card', icon: 'mdi:water', name: 'Portata L/min',
          entities: [{ entity: `sensor.irrigazione_portata_${s}`, name: 'L/min', color: '#3b82f6' }],
          hours_to_show: 24, points_per_hour: 6, line_width: 2,
          card_mod: gcm,
        },
      ];
      // Add pump graph only if sensor exists
      if (this._hass.states[`sensor.irrigazione_pompa_w_${s}`]) {
        irrCards.push({
          type: 'custom:mini-graph-card', icon: 'mdi:lightning-bolt', name: 'Potenza Pompa W',
          entities: [{ entity: `sensor.irrigazione_pompa_w_${s}`, name: 'Pompa W', color: '#f59e0b' }],
          hours_to_show: 24, points_per_hour: 6, line_width: 2,
          card_mod: gcm,
        });
      }
      this._popup('Grafico', { type: 'vertical-stack', cards: irrCards });
      return;
    }

    this._popup('Grafico', {
      type: 'vertical-stack', cards: [
        {
          type: 'custom:mini-graph-card', icon: 'mdi:chart-bar', name: 'Andamento Potenza',
          entities: [{ entity: `sensor.potenza_elettrodomestici_w_${s}`, name: 'Potenza W', color: '#1e90ff' }],
          hours_to_show: 24, points_per_hour: 6, line_width: 2, lower_bound: 0,
          card_mod: gcm,
        },
      ],
    });
  }

  _showInfo() {
    const s = this._slot;
    const _isIrr = (
      this._hass.states[`sensor.irrigazione_time_on_${s}`]   !== undefined ||
      this._hass.states[`sensor.irrigazione_portata_${s}`]   !== undefined
    );
    // Unified info popup — same for all device types
    // mastId = device master sensor (appliance or irrigation)
    const infoMastId = _isIrr
      ? `sensor.irrigazione_time_on_${s}`
      : `sensor.time_on_elettrodomestici_${s}`;
    const ver   = _isIrr
      ? (this._hass.states[infoMastId]?.attributes?.versione || '—')
      : this._s(`sensor.versione_elettrodomestici_${s}`, '—');
    const upd   = this._s('sensor.aggiornamento_elettrodomestici_hub', '—');
    const maint = this._a(infoMastId, 'manutenzione', '—');
    const rst   = this._a(infoMastId, 'ultimo_reset', '—');
    this._popup('Info', {
      type: 'markdown',
      card_mod: { style: 'ha-card{background:var(--card-background-color);color:var(--primary-text-color)!important;}ha-markdown,.markdown-body{color:var(--primary-text-color)!important;}' },
      content: `## Elettrodomestico Monitor\n\n**Versione:** ${ver}\n\n**Aggiornamento:** ${upd}\n\n**Manutenzione:** ${maint}\n\n**Ultimo reset:** ${rst}`,
    });
  }

  getCardSize() { return 4; }
}

// Guard against double registration (e.g. two Lovelace resource entries)
if (!customElements.get('elettrodomestico-monitor-card')) {
  customElements.define('elettrodomestico-monitor-card', ElettrodomesticoMonitorCard);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'elettrodomestico-monitor-card',
  name: 'Elettrodomestico Monitor Card',
  description: 'v4.27 — Shadow DOM nativo, popup browser_mod',
  preview: true,
});

console.info(
  '%c ELETTRODOMESTICO MONITOR %c v4.27 ',
  'background:#12203a;color:#00d4ff;font-weight:bold;padding:2px 8px;border-radius:3px 0 0 3px',
  'background:#00d4ff;color:#12203a;font-weight:bold;padding:2px 8px;border-radius:0 3px 3px 0'
);
