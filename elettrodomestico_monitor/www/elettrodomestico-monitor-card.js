/**
 * Elettrodomestico Monitor Card v6.2.1
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

  // Escape minimale prima di interpolare in innerHTML: this._config.name è
  // testo libero impostato dall'utente nella configurazione della card
  // (spesso copiata da dashboard condivise online) — senza escape un nome
  // tipo '<img src=x onerror=...>' eseguirebbe come HTML/JS.
  static _esc(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }
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
    // Normalize slot to a single 'x'-prefixed token (mirrors Python naming.slot_token).
    // Guards against a double-prefix ('xx1') if cfg.slot already includes 'x'.
    this._slot    = (() => { const s = String(cfg.slot ?? '').trim();
      return (s.startsWith('x') && /^\d+$/.test(s.slice(1))) ? s : `x${s}`; })();
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
          <span id="hdr" style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${ElettrodomesticoMonitorCard._esc(this._config.name || 'Elettrodomestico')}</span>
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
      this._hass.states[this._eidOf('portata', `sensor.irrigazione_portata_${s}`)]   !== undefined ||
      this._hass.states[this._eidOf('pompa', `sensor.irrigazione_pompa_w_${s}`)]   !== undefined
    );

    const mastId = _isIrr
      ? irrMastId
      : `sensor.time_on_elettrodomestici_${s}`;
    const acId   = _isIrr
      ? irrMastId   // use irrigazione master for "is active" check
      : `binary_sensor.ac_elettrodomestici_${s}`;
    const pwId   = _isIrr
      ? this._eidOf('portata', `sensor.irrigazione_portata_${s}`)
      : this._eidOf('power', `sensor.potenza_elettrodomestici_w_${s}`);
    const pw2Id  = _isIrr
      ? this._eidOf('pompa', `sensor.irrigazione_pompa_w_${s}`)
      : null;
    const batId   = this._eidOf('batteria', `sensor.batteria_vacuum_${s}`);
    const nmId    = `text.nome_elettrodomestico_${s}`;
    const ma      = this._hass.states[mastId]?.attributes || {};
    // For climate devices read hvac_mode from the wrapper entity (reactive,
    // updated immediately) instead of ac_state from the coordinator (20s lag).
    const _climaWrapEid = ma.preset === 'clima'
      ? this._eidOf('climate', `climate.elettrodomestici_${s}`)
      : null;
    const _climaWrapSt  = _climaWrapEid ? this._hass.states[_climaWrapEid] : null;
    const isOn    = _isIrr
      ? (ma.ciclo_attivo === true)
      : _climaWrapSt
        ? (_climaWrapSt.state !== 'off' && _climaWrapSt.state !== 'unavailable' && _climaWrapSt.state !== 'unknown')
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
    // LOGIC: Green = HA can communicate with the device. Red = entity is unavailable.
    // Priority depends on what is configured for each device type.
    const _offline_states = new Set(['unavailable', 'unknown']);
    const _avail = st => st !== undefined && !_offline_states.has(st?.state ?? 'unavailable');

    let _isOnline;
    if (_isIrr) {
      // IRRIGATION: check real zone switches (from zone config) + flow/pump sensors
      const irrAttrs   = this._hass.states[`sensor.irrigazione_time_on_${s}`]?.attributes || {};
      const flowEid    = irrAttrs.flow_sensor_eid  || '';
      const pumpEid    = irrAttrs.pump_sensor_eid  || '';
      const realZoneSws = Array.isArray(irrAttrs.real_zone_switches)
        ? irrAttrs.real_zone_switches.filter(Boolean) : [];

      // Each configured entity must exist and not be unavailable
      const _zonesOk = realZoneSws.length === 0
        || realZoneSws.every(eid => _avail(this._hass.states[eid]));
      const _flowOk  = !flowEid  || _avail(this._hass.states[flowEid]);
      const _pumpOk  = !pumpEid  || _avail(this._hass.states[pumpEid]);

      // Need at least one check to make a determination
      const _hasAny  = realZoneSws.length > 0 || flowEid || pumpEid;
      _isOnline = _hasAny ? (_zonesOk && _flowOk && _pumpOk) : true;

    } else {
      // NON-IRRIGATION:
      // 1. Power sensor → use coordinator's sensor_online flag (most reliable)
      // 2. Battery sensor (vacuum) → check directly
      // 3. Trigger entity (clima/vacuum) → check directly
      // 4. Switch only (no power sensor) → 'unavailable' = offline, 'on'/'off' = online
      // 5. Fallback → true (coordinator is running)

      const _hasPwr    = !!ma.has_power_sensor;  // true only if real power sensor configured
      const _batEid    = this._eidOf('batteria', `sensor.batteria_vacuum_${s}`);
      const _batSt     = this._hass.states[_batEid];
      const _trigEid   = ma.trigger_entity || '';
      const _trigSt    = _trigEid ? this._hass.states[_trigEid] : undefined;
      const _swState   = ma.switch_state;
      // Climate devices often have BOTH a (local) power sensor for consumption
      // AND a cloud climate entity for state. When the internet drops, the power
      // sensor stays online but the climate entity goes unavailable. For these,
      // availability must follow the CLIMATE entity, not the power sensor.
      // Detect climate from the BACKEND preset (not the YAML flag), and read the
      // real climate entity's state that the coordinator already exposes.
      const _isClimaDev = this._isClima || ma.preset === 'clima';
      let _climaSt;
      if (_isClimaDev) {
        _climaSt = _trigSt
          ?? this._hass.states[this._eidOf('climate', `climate.elettrodomestici_${s}`)]
          ?? (_trigEid ? this._hass.states[_trigEid] : undefined);
      }

      if (_isClimaDev) {
        // Climate: trust the real climate entity. Offline if its state is
        // unavailable/unknown, or if the coordinator reports the trigger gone.
        const _ts = (_climaSt?.state) ?? ma.trigger_state;
        _isOnline = _ts !== undefined && _ts !== null
          && _ts !== 'unavailable' && _ts !== 'unknown';
      } else if (_hasPwr) {
        // Device has power sensor: sensor_online flag is set by coordinator on every reading
        _isOnline = ma.sensor_online !== false;
      } else if (_batSt !== undefined) {
        // Vacuum: battery sensor is always polled when device is reachable
        _isOnline = _avail(_batSt);
      } else if (_trigSt !== undefined) {
        // Clima or trigger-based device
        _isOnline = _avail(_trigSt);
      } else if (_swState !== undefined && _swState !== null) {
        // Switch-only device: only 'unavailable'/'unknown' means offline
        _isOnline = _swState !== 'unavailable' && _swState !== 'unknown';
      } else {
        // No sensors configured — coordinator running means we're online
        _isOnline = true;
      }
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
      // Compare against the browser-normalized absolute URL to avoid reloading
      // the same image on every state update (which restarts animated GIFs).
      const resolved = new URL(src, document.baseURI).href;
      if (imgEl.src !== resolved) imgEl.src = src;
    } else {
      ico.style.display = '';
      imgEl.style.display = 'none';
    }

    // 4 info rows
    let term, dur, cons, cost;
    if (_isIrr) {
      // Read from irrigation master sensor attributes
      const irrAttr = this._hass.states[`sensor.irrigazione_time_on_${s}`]?.attributes || {};
      term = isOn
        ? (irrAttr.zona_attiva || 'Irrigazione attiva')
        : (irrAttr.zona_ultima || '—');
      dur  = irrAttr.tempo_oggi || '—';
      cons = irrAttr.litri_oggi !== undefined ? `${irrAttr.litri_oggi} L` : '—';
      // Total cost = water cost + pump (kWh) cost
      const _ca = parseFloat(irrAttr.costo_acqua_oggi) || 0;
      const _ck = parseFloat(irrAttr.costo_kwh_oggi) || 0;
      cost = Math.round((_ca + _ck) * 100) / 100;
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
    this._q('#lbl3').textContent = _isIrr ? '€ Totale' : (isOn ? 'Costo Attuale' : 'Costo Ultimo');
    this._q('#val3').textContent = _isIrr
      ? ((cost !== undefined && cost !== null && cost !== '') ? `${cost} €` : '0 €')
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
      const hasPump = this._hass?.states[this._eidOf('pompa', `sensor.irrigazione_pompa_w_${s}`)] !== undefined;
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
            row.addEventListener('click', () => this._moreInfo(this._eidOf('pompa', `sensor.irrigazione_pompa_w_${s}`)));
            track2.addEventListener('click', () => this._moreInfo(this._eidOf('pompa', `sensor.irrigazione_pompa_w_${s}`)));
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
      // Adapt the instantaneous bar to the source unit: water → L/min,
      // gas → m³/h, everything else → W/kW.
      const _su = this._hass?.states[`sensor.time_on_elettrodomestici_${s}`]?.attributes?.source_unit || 'W';
      const _isFlow = (_su === 'L/min' || _su === 'l/min');
      const _isGasH = (_su === 'm³/h' || _su === 'm3/h');
      const barLbl = this._q('.bar-lbl');
      if (_isFlow || _isGasH) {
        const unit = _isFlow ? 'L/min' : 'm³/h';
        const max  = this._config.max_flow || (_isFlow ? 30 : 10);
        const pct  = Math.min(100, Math.max(0, (pwW / max) * 100));
        const clr  = pwW > 0 ? '#3b82f6' : '#94a3b8';
        if (barLbl) barLbl.textContent = 'Consumo Istantaneo';
        this._q('#bico').textContent = '💧';
        this._q('#bval').textContent = `${pwW.toFixed(1)} ${unit}`;
        this._q('#bval').style.color = clr;
        this._q('#bfill').style.width = `${pct}%`;
        this._q('#bfill').style.backgroundColor = clr;
      } else {
        if (barLbl) barLbl.textContent = 'Consumo Istantaneo';
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

  // Find the battery-return number entity for this slot. Prefers the canonical
  // id, but if HA appended a registry suffix (e.g. _2 after a device was
  // recreated), fall back to any number entity matching the slot. Returns the
  // canonical id even if missing, so the row shows a clear (not crashing) state.
  _findVacReturnEntity(s) {
    // Prefer the backend-resolved id from the eids map (single source of truth).
    const fromMap = this._eidOf('soglia_rientro', null);
    if (fromMap && this._hass?.states[fromMap] !== undefined) return fromMap;
    const canonical = fromMap || `number.soglia_rientro_vacuum_${s}`;
    const states = this._hass?.states || {};
    if (states[canonical] !== undefined) return canonical;
    const match = Object.keys(states).find(eid =>
      eid.startsWith(`number.soglia_rientro_vacuum_${s}`));
    return match || canonical;
  }

  // Resolve an entity_id from the backend-provided eids map (single source of
  // truth via naming.py). Falls back to the legacy manual pattern only if the
  // map isn't present yet, so older backends keep working during upgrades.
  _eidOf(logical, fallback) {
    const s = this._slot;
    const irrMaster = `sensor.irrigazione_time_on_${s}`;
    const appMaster = `sensor.time_on_elettrodomestici_${s}`;
    const masterEid = (this._hass?.states[irrMaster] !== undefined) ? irrMaster : appMaster;
    const map = this._hass?.states[masterEid]?.attributes?.eids;
    if (map && map[logical]) return map[logical];
    return fallback;
  }

  _moreInfo(eid) {
    this.dispatchEvent(new CustomEvent('hass-more-info', {
      bubbles: true, composed: true, detail: { entityId: eid },
    }));
  }

  // Shared 3-table stats popup (Ciclo Corrente + Periodo Corrente + Periodi
  // Precedenti). Appliance and irrigation pass their own columns/rows; the
  // common vertical-stack structure lives here to avoid duplication.
  _statsPopup(title, currentRows, headers, rowsNow, rowsPrev) {
    const dbg = !!this._config?.debug;
    this._popup(title, {
      type: 'vertical-stack',
      cards: [
        { type: 'custom:em-stat-table', title: '⚙️ Ciclo Corrente',
          headers: ['', 'Valore'], rows: currentRows, debug: dbg },
        { type: 'custom:em-stat-table', title: '📊 Periodo Corrente',
          headers, rows: rowsNow, debug: dbg },
        { type: 'custom:em-stat-table', title: '🗓️ Periodi Precedenti',
          headers, rows: rowsPrev, debug: dbg },
      ],
    });
  }


  // ── Wire ─────────────────────────────────────────────────────────────────────

  _wire() {
    const s = this._slot;
    const _isIrr = (
      this._hass?.states[`sensor.irrigazione_time_on_${s}`]   !== undefined ||
      this._hass?.states[this._eidOf('portata', `sensor.irrigazione_portata_${s}`)]   !== undefined ||
      this._hass?.states[this._eidOf('pompa', `sensor.irrigazione_pompa_w_${s}`)]   !== undefined
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
        this._eidOf('climate', `climate.elettrodomestici_${s}`),
        this._eidOf('switch', `switch.switch_elettrodomestici_${s}`),
        `binary_sensor.ac_elettrodomestici_${s}`,
      ];
      const found = ents.find(e => this._hass?.states[e] !== undefined);
      if (found) this._moreInfo(found);
    });

    // Image → 7 giorni
    this._q('#img-wrap').addEventListener('click', () => {
      // Consumption unit adapts to the source: L (water), m³ (gas), kWh (power)
      const _tu = this._hass.states[`sensor.time_on_elettrodomestici_${s}`]?.attributes?.total_unit
                || this._hass.states[`sensor.time_on_elettrodomestici_${s}`]?.attributes?.source_unit || 'kWh';
      const _consUnit = _isIrr ? 'L'
                      : (_tu === 'L/min' || _tu === 'l/min' || _tu === 'L') ? 'L'
                      : (_tu === 'm³/h' || _tu === 'm³' || _tu === 'm3') ? 'm³' : 'kWh';
      this._popup('Ultimi 7 Giorni', {
        type: 'entities', card_mod: cm(),
        entities: [
          { type: 'divider' },
          ...DAYS_IT.flatMap((d, i) => ([
            {
              entity: `sensor.settimana_${d}_elettrodomestici_${s}`,
              name: DAYS_LABEL[i],
              type: 'custom:multiple-entity-row',
              state_header: _isIrr ? 'L' : _consUnit,
              state_color: false, icon: 'mdi:calendar',
              entities: _isIrr ? [
                { attribute: 'cicli', name: 'CICLI' },
                { attribute: 'tempo', name: 'TEMPO' },
                { attribute: 'kwh', name: 'kWh' },
                { attribute: 'costo_kwh', name: '€ Pompa', unit: '€' },
                { attribute: 'costo_acqua', name: '€ Acqua', unit: '€' },
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

    // Info rows → more-info (distinct sensors so each opens its own graph)
    const _ir0Target = _isIrr ? `sensor.irrigazione_time_on_${s}` : this._eidOf('tempo_oggi', `sensor.tempo_oggi_elettrodomestici_${s}`);
    this._q('#ir0').addEventListener('click', () => this._moreInfo(_ir0Target));
    const _ir1Target = _isIrr ? `sensor.irrigazione_time_on_${s}` : this._eidOf('ultimo_ciclo', `sensor.ultimo_ciclo_elettrodomestici_${s}`);
    this._q('#ir1').addEventListener('click', () => this._moreInfo(_ir1Target));
    const _ir2Target = _isIrr ? this._eidOf('litri_oggi', `sensor.irrigazione_litri_oggi_${s}`) : this._eidOf('energy_oggi', `sensor.energy_oggi_elettrodomestici_${s}`);
    this._q('#ir2').addEventListener('click', () => this._moreInfo(_ir2Target));
    const _ir3Target = _isIrr ? `sensor.irrigazione_time_on_${s}` : this._eidOf('costo_oggi', `sensor.costo_oggi_elettrodomestici_${s}`);
    this._q('#ir3').addEventListener('click', () => this._moreInfo(_ir3Target));

    // Bar click → HA native more-info (irrigation: portata sensor; others: power/battery)
    const _barClick = () => {
      const irrSensor = this._eidOf('portata', `sensor.irrigazione_portata_${s}`);
      const batSensor = this._eidOf('batteria', `sensor.batteria_vacuum_${s}`);
      const pwrSensor = this._eidOf('power', `sensor.potenza_elettrodomestici_w_${s}`);
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


  // Build a self-styled HTML table (inline styles → no card-mod dependency).
  // title: heading; headers: array of column names; rows: array of {label, cells:[...]}.

  // ── Irrigation settings popup content (reusable for back-navigation) ──
  _irrSettingsPopup(s, withBack = true) {
    // withBack controls one level of nesting only, to avoid a circular JSON reference:
    // settings(withBack=true) -> program -> back reopens settings(withBack=false) -> program (no back loop)
    const programData = this._irrProgramPopup(s, withBack);
    const programButton = {
      type: 'custom:button-card',
      entity: this._eidOf('programmazione', `switch.irrigazione_programmazione_${s}`),
      name: '🌳 Programmazione',
      icon: 'mdi:sprinkler-variant',
      show_state: false,
      styles: {
        card: [{ 'box-shadow': 'none' }, { 'background': 'none' }, { 'padding': '8px 4px' }],
        grid: [{ 'grid-template-areas': '"i n arrow"' }, { 'grid-template-columns': 'min-content 1fr min-content' }],
        name: [{ 'justify-self': 'start' }, { 'padding-left': '8px' }, { 'font-size': '14px' }, { 'color': 'var(--primary-text-color)' }],
        icon: [{ 'width': '24px' }, { 'color': 'var(--paper-item-icon-color)' }],
        custom_fields: { arrow: [{ 'color': 'var(--secondary-text-color)' }] },
      },
      custom_fields: { arrow: '<ha-icon icon="mdi:chevron-right"></ha-icon>' },
      tap_action: {
        action: 'fire-dom-event',
        browser_mod: { service: 'browser_mod.popup', data: programData },
      },
    };
    return {
      title: 'Impostazioni Irrigazione',
      content: {
        type: 'entities', card_mod: this._cm(),
        entities: [
          { type: 'divider' },
          { entity: 'sensor.time', name: 'Orologio', icon: 'mdi:clock-outline' },
          { type: 'divider' },
          {
            entity: `sensor.irrigazione_time_on_${s}`,
            attribute: 'notifiche_fine',
            name: 'Fascia Oraria Notifiche', icon: 'mdi:timer-outline',
            type: 'custom:multiple-entity-row', state_header: 'FINE',
            entities: [{ entity: `sensor.irrigazione_time_on_${s}`, attribute: 'notifiche_inizio', name: 'INIZIO' }],
          },
          { type: 'divider' },
          {
            entity: this._eidOf('notify_push', `switch.notifica_push_elettrodomestici_${s}`),
            name: 'Notifiche', icon: 'mdi:bell',
            type: 'custom:multiple-entity-row', show_state: false,
            entities: [
              { entity: this._eidOf('notify_google', `switch.notifica_google_elettrodomestici_${s}`),   name: 'GOOGLE',   toggle: true },
              { entity: this._eidOf('notify_alexa', `switch.notifica_alexa_elettrodomestici_${s}`),    name: 'ALEXA',    toggle: true },
              { entity: this._eidOf('notify_whatsapp', `switch.notifica_whatsapp_elettrodomestici_${s}`), name: 'WHATSAPP', toggle: true },
              { entity: this._eidOf('notify_push', `switch.notifica_push_elettrodomestici_${s}`),     name: 'PUSH',     toggle: true },
            ],
          },
          { type: 'divider' },
          { entity: this._eidOf('master_switch', `switch.irrigazione_master_${s}`), name: 'Stato Ciclo', icon: 'mdi:state-machine' },
          { entity: `text.nome_irrigazione_${s}`, name: 'Nome', icon: 'mdi:rename-box' },
          { type: 'divider' },
          programButton,
          { type: 'divider' },
          { entity: this._eidOf('manutenzione', `button.manutenzione_elettrodomestici_${s}`), name: 'Registra Manutenzione', icon: 'mdi:wrench-clock' },
          { entity: this._eidOf('reset', `button.reset_contatori_elettrodomestici_${s}`), name: 'Reset Contatori', icon: 'mdi:restore' },
          { type: 'divider' },
        ],
      },
    };
  }

  // ── Garden program sub-popup content (orari + giorni colorati + zone) ──
  // withBack: if true, include a Back button that reopens settings (one level only, no JSON cycle)
  _irrProgramPopup(s, withBack = false) {
    const DAYS_IT    = ['lunedi','martedi','mercoledi','giovedi','venerdi','sabato','domenica'];
    const DAYS_LABEL = ['L','M','M','G','V','S','D'];

    // 7 day buttons: green if ON (active), red if OFF (inactive)
    const dayButtons = {
      type: 'horizontal-stack',
      cards: DAYS_IT.map((d, i) => ({
        type: 'custom:button-card',
        entity: `switch.irrigazione_${d}_${s}`,
        name: DAYS_LABEL[i],
        show_icon: false, show_state: false,
        tap_action: { action: 'toggle' },
        styles: {
          card: [
            { 'border-radius': '50%' },
            { 'aspect-ratio': '1 / 1' },
            { 'box-shadow': 'none' },
            { 'padding': '0px' },
          ],
          name: [{ 'font-size': '15px' }, { 'font-weight': 'bold' }],
        },
        state: [
          { value: 'on',  styles: { card: [{ 'background-color': 'rgba(76,175,80,0.85)' }], name: [{ 'color': '#fff' }] } },
          { value: 'off', styles: { card: [{ 'background-color': 'rgba(244,67,54,0.20)' }], name: [{ 'color': 'var(--disabled-text-color)' }] } },
        ],
      })),
    };

    // Orari: 2 rows (Orario 1+2 on row 1, Orario 3 on row 2) via multiple-entity-row
    return {
      title: 'Programmazione',
      style: '--popup-background-color: var(--card-background-color); --dialog-backdrop-filter: blur(2em) brightness(0.75);',
      content: {
        type: 'vertical-stack',
        cards: [
          ...(withBack ? [{
            type: 'custom:button-card',
            name: '← Indietro alle Impostazioni',
            icon: 'mdi:arrow-left',
            show_state: false,
            styles: {
              card: [{ 'box-shadow': 'none' }, { 'background': 'none' }, { 'padding': '6px 4px' }],
              grid: [{ 'grid-template-areas': '"i n"' }, { 'grid-template-columns': 'min-content 1fr' }],
              name: [{ 'justify-self': 'start' }, { 'padding-left': '8px' }, { 'font-size': '14px' }, { 'color': 'var(--primary-color)' }],
              icon: [{ 'width': '22px' }, { 'color': 'var(--primary-color)' }],
            },
            tap_action: {
              action: 'fire-dom-event',
              browser_mod: { service: 'browser_mod.popup', data: this._irrSettingsPopup(s, false) },
            },
          }] : []),
          {
            type: 'entities', card_mod: this._cm(),
            entities: [
              { type: 'divider' },
              { entity: this._eidOf('master_switch', `switch.irrigazione_master_${s}`), name: '▶ Avvia Manualmente Ciclo', icon: 'mdi:sprinkler-variant' },
              { type: 'divider' },
              { entity: this._eidOf('programmazione', `switch.irrigazione_programmazione_${s}`), name: '📅 Programmazione Automatica', icon: 'mdi:calendar-clock' },
              { type: 'divider' },
              {
                entity: `time.irrigazione_s1_orario_${s}`,
                name: 'Orari', icon: 'mdi:clock-start',
                type: 'custom:multiple-entity-row', show_state: false,
                entities: [
                  { entity: `time.irrigazione_s1_orario_${s}`, name: '1' },
                  { entity: `time.irrigazione_s2_orario_${s}`, name: '2' },
                  { entity: `time.irrigazione_s3_orario_${s}`, name: '3' },
                ],
              },
              { type: 'section', label: 'Giorni Attivi' },
            ],
          },
          dayButtons,
          {
            type: 'entities', card_mod: this._cm(),
            entities: [
              { type: 'section', label: 'Zone — Durata e Controllo Manuale' },
              ...(Object.keys(this._hass.states)
                .filter(e => e.startsWith(`switch.irrigazione_z`) && e.endsWith(`_${s}`))
                .sort()
                .flatMap(sw => {
                  const zNum = sw.match(/irrigazione_z(\d+)_/)?.[1];
                  const numEid = zNum ? `number.irrigazione_z${zNum}_durata_${s}` : null;
                  const rows = [{ entity: sw, icon: 'mdi:water' }];
                  if (numEid && this._hass.states[numEid]) {
                    rows.push({ entity: numEid, name: `Durata Zona ${zNum}`, icon: 'mdi:timer' });
                  }
                  return rows;
                })),
              { type: 'divider' },
            ],
          },
        ],
      },
    };
  }

    _showSettings() {
    const s = this._slot;
    const irrMastId = `sensor.irrigazione_time_on_${s}`;
    const _isIrr = (
      this._hass?.states[`sensor.irrigazione_time_on_${s}`]   !== undefined ||
      this._hass?.states[this._eidOf('portata', `sensor.irrigazione_portata_${s}`)]   !== undefined ||
      this._hass?.states[this._eidOf('pompa', `sensor.irrigazione_pompa_w_${s}`)]   !== undefined
    );
    // Threshold unit adapts to the source: water/gas show flow units, else Watt
    const _srcUnit = this._hass?.states[`sensor.time_on_elettrodomestici_${s}`]?.attributes?.source_unit || 'W';
    const _sogliaHdr = (_srcUnit === 'L/min' || _srcUnit === 'l/min') ? 'L/min'
                     : (_srcUnit === 'm³/h' || _srcUnit === 'm3/h') ? 'm³/h' : 'W';

    if (_isIrr) {
      // ── Irrigation settings popup (uniform with appliance layout) ────────
      const p = this._irrSettingsPopup(s);
      this._popup(p.title, p.content);
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
          entity: this._eidOf('programma', `sensor.programma_elettrodomestici_${s}`),
          attribute: 'notifiche_fine',
          name: 'Fascia Oraria Notifiche', icon: 'mdi:timer-outline',
          type: 'custom:multiple-entity-row', state_header: 'FINE',
          entities: [{ entity: this._eidOf('programma', `sensor.programma_elettrodomestici_${s}`), attribute: 'notifiche_inizio', name: 'INIZIO' }],
        },
        { type: 'divider' },
        {
          entity: this._eidOf('notify_push', `switch.notifica_push_elettrodomestici_${s}`),
          name: 'Notifiche', icon: 'mdi:bell',
          type: 'custom:multiple-entity-row', show_state: false,
          entities: [
            { entity: this._eidOf('notify_google', `switch.notifica_google_elettrodomestici_${s}`),   name: 'GOOGLE',   toggle: true },
            { entity: this._eidOf('notify_alexa', `switch.notifica_alexa_elettrodomestici_${s}`),    name: 'ALEXA',    toggle: true },
            { entity: this._eidOf('notify_whatsapp', `switch.notifica_whatsapp_elettrodomestici_${s}`), name: 'WHATSAPP', toggle: true },
            { entity: this._eidOf('notify_push', `switch.notifica_push_elettrodomestici_${s}`),     name: 'PUSH',     toggle: true },
          ],
        },
        { type: 'divider' },
        { entity: `binary_sensor.ac_elettrodomestici_${s}`, name: 'Stato Ciclo', icon: 'mdi:state-machine' },
        { entity: `text.messaggio_elettrodomestico_${s}`, name: 'Messaggio', icon: 'mdi:message-text' },
        { type: 'divider' },
        {
          entity: `sensor.time_on_elettrodomestici_${s}`,
          name: 'Soglia / Ritardi', icon: 'mdi:flash',
          type: 'custom:multiple-entity-row', state_header: _sogliaHdr,
          entities: [
            { entity: this._eidOf('soglia', `number.soglia_lavoro_elettrodomestici_w_${s}`), name: 'SOGLIA' },
            { entity: this._eidOf('tempo_innesco', `number.tempo_innesco_elettrodomestici_m_${s}`), name: 'RITARDO OFF' },
            { entity: this._eidOf('avvio_ritardato', `number.avvio_ritardato_elettrodomestici_s_${s}`), name: 'RITARDO ON' },
          ],
        },
        { type: 'divider' },
        { entity: this._eidOf('auto_on', `time.orario_accensione_elettrodomestici_${s}`), name: 'Auto ON', icon: 'mdi:clock-start' },
        { entity: this._eidOf('auto_off', `time.orario_spegnimento_elettrodomestici_${s}`), name: 'Auto OFF', icon: 'mdi:clock-end' },
        ...(this._isVac ? [
          { entity: this._findVacReturnEntity(s), name: 'Auto OFF Batteria', icon: 'mdi:battery-alert' },
        ] : []),
        { type: 'divider' },
        { entity: this._eidOf('manutenzione', `button.manutenzione_elettrodomestici_${s}`), name: 'Registra Manutenzione', icon: 'mdi:wrench-clock' },
        { entity: this._eidOf('reset', `button.reset_contatori_elettrodomestici_${s}`), name: 'Reset Contatori', icon: 'mdi:restore' },
        { type: 'divider' },
        { entity: this._eidOf('costo_energia', `sensor.costo_energia_elettrodomestici_${s}`), name: 'Costo Energia', icon: 'mdi:currency-eur' },
        { type: 'divider' },
      ],
    });
  }

  _showIrrStats(s) {
    const mid = `sensor.irrigazione_time_on_${s}`;
    const fvOn = this._hass.states[mid]?.attributes?.fv_enabled === true;

    const headers = fvOn
      ? ['Periodo','Cicli','Tempo','L','kWh','€ Acqua','€ Pompa','€ Rete','€ Sole','€ Tot']
      : ['Periodo','Cicli','Tempo','L','kWh','€ Acqua','€ Pompa','€ Tot'];
    // A (Tempo): nessun sensore dedicato per-periodo esiste per questa
    // colonna — prima il click ripiegava silenziosamente su 'mid' (il
    // sensore aggregato time_on), aprendo un grafico non pertinente
    // rispetto al valore Oggi/Mese/Anno effettivamente cliccato.
    const A = (attr) => ({ entity: mid, attr, raw: true, noClick: true });
    const C = (attr, period) => ({ entity: mid, attr, integer: true,
      clickEntity: period ? `sensor.irrigazione_cicli_${period}_${s}` : undefined,
      noClick: period ? false : true });
    const L = (attr, period) => ({ entity: mid, attr, decimals: 2,
      clickEntity: period ? `sensor.irrigazione_litri_${period}_${s}` : undefined,
      noClick: period ? false : true });
    const K = (attr, period) => ({ entity: mid, attr,
      clickEntity: period ? `sensor.irrigazione_kwh_${period}_${s}` : undefined,
      noClick: period ? false : true });
    // Cost cells → dedicated cost sensors (clickable history).
    // Per le righe 'Periodi Precedenti' (period non passato: Ieri/Mese
    // Prec./Anno Prec.) NON esiste un sensore dedicato per quello
    // specifico valore storico — prima il click ripiegava su 'mid',
    // aprendo il grafico del sensore time_on (durata, non costo): esattamente
    // il bug segnalato ("apre Time On invece del costo"). Ora disabilitato
    // esplicitamente invece di mostrare un grafico sbagliato.
    const Ca = (attr, period) => ({ entity: mid, attr, euro: true,
      clickEntity: period ? `sensor.irrigazione_costo_acqua_${period}_${s}` : undefined,
      noClick: period ? false : true });
    const Ck = (attr, period) => ({ entity: mid, attr, euro: true,
      clickEntity: period ? `sensor.irrigazione_costo_kwh_${period}_${s}` : undefined,
      noClick: period ? false : true });
    const Cr = (attr, period) => ({ entity: mid, attr, euro: true,
      clickEntity: period ? `sensor.irrigazione_costo_rete_${period}_${s}` : undefined,
      noClick: period ? false : true });
    const Cs = (attr, period) => ({ entity: mid, attr, euro: true,
      clickEntity: period ? `sensor.irrigazione_costo_sole_${period}_${s}` : undefined,
      noClick: period ? false : true });
    const Tot = (ca, ck, period) => ({ entity: mid, sum: [ca, ck], euro: true,
      clickEntity: period ? `sensor.irrigazione_costo_tot_${period}_${s}` : undefined,
      noClick: period ? false : true });
    const mkRow = (lbl, c, t, l, k, ca, ck, cr, cs, period) => ({
      label: lbl,
      cells: fvOn
        ? [{text:lbl}, C(c,period), A(t), L(l,period), K(k,period), Ca(ca,period), Ck(ck,period), Cr(cr,period), Cs(cs,period), Tot(ca,ck,period)]
        : [{text:lbl}, C(c,period), A(t), L(l,period), K(k,period), Ca(ca,period), Ck(ck,period), Tot(ca,ck,period)],
    });
    const rowsNow = [
      mkRow('Oggi','cicli_oggi','tempo_oggi','litri_oggi','kwh_oggi','costo_acqua_oggi','costo_kwh_oggi','costo_rete_oggi','risparmio_sole_oggi','oggi'),
      mkRow('Mese','cicli_mese','tempo_mese','litri_mese','kwh_mese','costo_acqua_mese','costo_kwh_mese','costo_rete_mese','risparmio_sole_mese','mese'),
      mkRow('Anno','cicli_anno','tempo_anno','litri_anno','kwh_anno','costo_acqua_anno','costo_kwh_anno','costo_rete_anno','risparmio_sole_anno','anno'),
    ];
    const rowsPrev = [
      mkRow('Ieri','cicli_ieri','tempo_ieri','l_ieri','kwh_ieri','costo_acqua_ieri','costo_kwh_ieri','costo_rete_ieri','risparmio_sole_ieri'),
      mkRow('Mese Prec.','cicli_mese_prec','tempo_mese_prec','l_mese_prec','kwh_mese_prec','costo_acqua_mese_prec','costo_kwh_mese_prec','costo_rete_mese_prec','risparmio_sole_mese_prec'),
      mkRow('Anno Prec.','cicli_anno_prec','tempo_anno_prec','l_anno_prec','kwh_anno_prec','costo_acqua_anno_prec','costo_kwh_anno_prec','costo_rete_anno_prec','risparmio_sole_anno_prec'),
    ];

    this._statsPopup('Statistiche Irrigazione', [
      { cells: [{text:'Stato'},         {entity:mid, attr:'zona_attiva', raw:true, fallback:'Fermo'}] },
      { cells: [{text:'Tempo Ciclo'},   {entity:mid, attr:'tempo_oggi', raw:true, fallback:'0min'}] },
      { cells: [{text:'Consumo Ciclo'}, {entity:mid, attr:'litri_oggi', decimals:2, suffix:' L', fallback:'0 L'}] },
    ], headers, rowsNow, rowsPrev);
  }

    _showStats() {
    const s = this._slot;
    const _isIrr = (
      this._hass.states[`sensor.irrigazione_time_on_${s}`]   !== undefined ||
      this._hass.states[this._eidOf('portata', `sensor.irrigazione_portata_${s}`)]   !== undefined
    );

    if (_isIrr) {
      this._showIrrStats(s);
      return;
    }

    // ── Standard appliance stats (custom em-stat-table: styled, all inline) ──
    const mid = `sensor.time_on_elettrodomestici_${s}`;
    const mAttr = this._hass.states[mid]?.attributes || {};
    const unit = mAttr.total_unit || 'kWh';
    // FV split only makes sense for energy (kWh); hide it for water/gas (L, m³)
    const _fvOn = (mAttr.fv_enabled === true) && (unit === 'kWh');

    const headers = _fvOn
      ? ['Periodo','Cicli','Tempo','Consumo','€ Rete','€ Sole','€ Tot']
      : ['Periodo','Cicli','Tempo','Consumo','€ Tot'];
    // Water/gas consumption → 2 decimals (40,05 L); energy (kWh) left as-is.
    const consDec = (unit === 'kWh') ? {} : { decimals: 2 };
    // All cells point to dedicated sensors (clickable history) where available.
    const rNow = (lbl, period, costAttr, reteAttr, soleAttr) => ({
      label: lbl,
      cells: _fvOn
        ? [{text:lbl}, {state:`sensor.cicli_${period}_elettrodomestici_${s}`,integer:true}, {state:`sensor.tempo_${period}_elettrodomestici_${s}`,raw:true,fallback:'0min'}, {state:`sensor.energy_${period}_elettrodomestici_${s}`,suffix:` ${unit}`,...consDec}, {entity:mid,attr:reteAttr,euro:true,clickEntity:`sensor.costo_rete_${period}_${s}`}, {entity:mid,attr:soleAttr,euro:true,clickEntity:`sensor.risparmio_sole_${period}_${s}`}, {entity:mid,attr:costAttr,euro:true,clickEntity:`sensor.costo_${period}_elettrodomestici_${s}`}]
        : [{text:lbl}, {state:`sensor.cicli_${period}_elettrodomestici_${s}`,integer:true}, {state:`sensor.tempo_${period}_elettrodomestici_${s}`,raw:true,fallback:'0min'}, {state:`sensor.energy_${period}_elettrodomestici_${s}`,suffix:` ${unit}`,...consDec}, {entity:mid,attr:costAttr,euro:true,clickEntity:`sensor.costo_${period}_elettrodomestici_${s}`}],
    });
    const rPrev = (lbl, period, tAttr, costAttr, reteAttr, soleAttr) => ({
      label: lbl,
      cells: _fvOn
        ? [{text:lbl}, {entity:`sensor.cicli_${period}_elettrodomestici_${s}`,lastPeriod:true,integer:true,clickEntity:`sensor.cicli_${period}_elettrodomestici_${s}`}, {entity:`sensor.tempo_${period}_elettrodomestici_${s}`,lastPeriod:true,raw:true,fallback:'0min'}, {entity:`sensor.energy_${period}_elettrodomestici_${s}`,lastPeriod:true,suffix:` ${unit}`,...consDec}, {entity:mid,attr:reteAttr,euro:true,noClick:true}, {entity:mid,attr:soleAttr,euro:true,noClick:true}, {entity:mid,attr:costAttr,euro:true,noClick:true}]
        : [{text:lbl}, {entity:`sensor.cicli_${period}_elettrodomestici_${s}`,lastPeriod:true,integer:true,clickEntity:`sensor.cicli_${period}_elettrodomestici_${s}`}, {entity:`sensor.tempo_${period}_elettrodomestici_${s}`,lastPeriod:true,raw:true,fallback:'0min'}, {entity:`sensor.energy_${period}_elettrodomestici_${s}`,lastPeriod:true,suffix:` ${unit}`,...consDec}, {entity:mid,attr:costAttr,euro:true,noClick:true}],
    });

    const rowsNow = [
      rNow('Oggi', 'oggi', 'costo_consumo_giornaliero_elettrodomestici', 'costo_rete_oggi', 'risparmio_sole_oggi'),
      rNow('Mese', 'mese', 'costo_consumo_mensile_elettrodomestici', 'costo_rete_mese', 'risparmio_sole_mese'),
      rNow('Anno', 'anno', 'costo_consumo_annuale_elettrodomestici', 'costo_rete_anno', 'risparmio_sole_anno'),
    ];
    const rowsPrev = [
      rPrev('Ieri', 'oggi', 'Ieri', 'costo_consumo_ieri_elettrodomestici', 'costo_rete_ieri', 'risparmio_sole_ieri'),
      rPrev('Mese Prec.', 'mese', 'Mese Precedente', 'costo_consumo_mese_precedente_elettrodomestici', 'costo_rete_mese_prec', 'risparmio_sole_mese_prec'),
      rPrev('Anno Prec.', 'anno', 'Anno Precedente', 'costo_consumo_anno_precedente_elettrodomestici', 'costo_rete_anno_prec', 'risparmio_sole_anno_prec'),
    ];

    this._statsPopup('Statistiche', [
      { cells: [{text:'Stato'},         {entity:mid, attr:'terminato', raw:true, fallback:'A riposo'}] },
      { cells: [{text:'Tempo Ciclo'},   {entity:mid, attr:'tempo_ciclo_elettrodomestici', raw:true, fallback:'—'}] },
      { cells: [{text:'Consumo Ciclo'}, {entity:mid, attr:'consumo_ciclo_elettrodomestici', raw:true, fallback:'—'}] },
    ], headers, rowsNow, rowsPrev);
  }

  _showUpdate() {
    const s = this._slot;
    // Version is hub-managed (single source of truth) — identical for ALL device types.
    // Both DISPONIBILE and INSTALLATA come from the hub update sensor attributes.
    const hubEid = 'sensor.aggiornamento_elettrodomestici_hub';
    this._popup('Update', {
      type: 'entities', card_mod: this._cm(),
      entities: [
        { type: 'divider' },
        { entity: 'switch.notifica_update_elettrodomestici_hub',
          name: 'Notifica Push Update', icon: 'mdi:bell-ring', state_color: true },
        { type: 'divider' },
        {
          entity: hubEid,
          attribute: 'versione_disponibile', name: 'DISPONIBILE', icon: 'mdi:update',
          type: 'custom:multiple-entity-row',
          entities: [{ entity: hubEid, attribute: 'versione_installata', name: 'INSTALLATA' }],
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
      this._hass.states[this._eidOf('portata', `sensor.irrigazione_portata_${s}`)]   !== undefined
    );

    if (_isIrr) {
      const irrCards = [
        {
          type: 'custom:mini-graph-card', icon: 'mdi:water', name: 'Portata L/min',
          entities: [{ entity: this._eidOf('portata', `sensor.irrigazione_portata_${s}`), name: 'L/min', color: '#3b82f6' }],
          hours_to_show: 24, points_per_hour: 6, line_width: 2,
          card_mod: gcm,
        },
      ];
      // Add pump graph only if sensor exists
      if (this._hass.states[this._eidOf('pompa', `sensor.irrigazione_pompa_w_${s}`)]) {
        irrCards.push({
          type: 'custom:mini-graph-card', icon: 'mdi:lightning-bolt', name: 'Potenza Pompa W',
          entities: [{ entity: this._eidOf('pompa', `sensor.irrigazione_pompa_w_${s}`), name: 'Pompa W', color: '#f59e0b' }],
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
          entities: [{ entity: this._eidOf('power', `sensor.potenza_elettrodomestici_w_${s}`), name: 'Potenza W', color: '#1e90ff' }],
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
      this._hass.states[this._eidOf('portata', `sensor.irrigazione_portata_${s}`)]   !== undefined
    );
    // Unified info popup — same for all device types
    // mastId = device master sensor (appliance or irrigation)
    const infoMastId = _isIrr
      ? `sensor.irrigazione_time_on_${s}`
      : `sensor.time_on_elettrodomestici_${s}`;
    const ver   = _isIrr
      ? (this._hass.states[infoMastId]?.attributes?.versione || '—')
      : this._s(this._eidOf('versione', `sensor.versione_elettrodomestici_${s}`), '—');
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
  description: 'v6.0.4 — Shadow DOM nativo, popup browser_mod',
  preview: true,
});

console.info(
  '%c ELETTRODOMESTICO MONITOR %c v6.0.4 ',
  'background:#12203a;color:#00d4ff;font-weight:bold;padding:2px 8px;border-radius:3px 0 0 3px',
  'background:#00d4ff;color:#12203a;font-weight:bold;padding:2px 8px;border-radius:0 3px 3px 0'
);
