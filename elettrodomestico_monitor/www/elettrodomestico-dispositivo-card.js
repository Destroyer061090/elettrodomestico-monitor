/**
 * Elettrodomestico Dispositivo Card v6.2.0
 * Card dedicata alla gestione ricarica batterie (preset "dispositivo").
 *
 * Config:
 *   type: custom:elettrodomestico-dispositivo-card
 *   slot: 301
 *   name: iPhone di Alex   # opzionale (sovrascrive il nome dal sensore)
 */

const DEV_CSS = `
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
.hdr {
  display:flex; align-items:center; justify-content:space-between;
  padding:12px 16px; border-bottom:1px solid rgba(255,255,255,0.08);
}
.hdr .title { font-size:1.05em; font-weight:600; }
.hdr .actions ha-icon { cursor:pointer; margin-left:10px; --mdc-icon-size:22px; color:var(--secondary-text-color); }
.body { padding:16px; display:flex; gap:18px; align-items:center; }
.ring { position:relative; width:104px; height:104px; flex:0 0 auto; }
.ring svg { transform:rotate(-90deg); }
.ring .pct {
  position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
  font-size:1.4em; font-weight:700;
}
.info { flex:1; display:flex; flex-direction:column; gap:6px; }
.row { display:flex; justify-content:space-between; font-size:0.92em; }
.row .lbl { color:var(--secondary-text-color); }
.row .val { font-weight:600; }
.statebadge { display:inline-flex; align-items:center; gap:5px; padding:3px 10px; border-radius:20px; font-size:0.82em; font-weight:600; }
.charging { background:rgba(76,175,80,0.18); color:#4caf50; }
.battery   { background:rgba(120,144,156,0.18); color:#90a4ae; }
.cycles { display:flex; gap:14px; padding:10px 16px; border-top:1px solid rgba(255,255,255,0.08); }
.cycles .c { flex:1; text-align:center; }
.cycles .c .n { font-size:1.15em; font-weight:700; }
.cycles .c .t { font-size:0.72em; color:var(--secondary-text-color); text-transform:uppercase; letter-spacing:0.4px; }
`;

class ElettrodomesticoDispositivoCard extends HTMLElement {

  // Vedi lo stesso helper in elettrodomestico-monitor-card.js: qui il
  // valore interpolato (_bat(), derivato da _slot) è tipicamente numerico,
  // ma _slot arriva comunque da una config YAML non validata a runtime —
  // escape difensivo per coerenza con le altre card.
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
    this._ready = false;
  }

  setConfig(cfg) {
    if (!cfg.slot) throw new Error('"slot" è obbligatorio');
    this._config = { ...cfg };
    this._slot   = `x${cfg.slot}`;
    this._ready  = false;
    this._build();
  }

  set hass(h) {
    this._hass = h;
    if (!this._ready) this._build();
    else this._update();
  }

  _q(sel) { return this.shadowRoot.querySelector(sel); }
  _bat()  { return `sensor.ricarica_dispositivo_${this._slot}`; }
  _a(attr, def='') { return this._hass?.states[this._bat()]?.attributes?.[attr] ?? def; }

  _build() {
    if (!this._config || !this._hass) return;
    this._ready = true;
    const name = this._config.name || this._a('friendly_name') || 'Dispositivo';
    this.shadowRoot.innerHTML = `
      <style>${DEV_CSS}</style>
      <div class="card">
        <div class="hdr">
          <span class="title" id="nm">${ElettrodomesticoDispositivoCard._esc(name)}</span>
          <span class="actions">
            <ha-icon id="bt-stats" icon="mdi:chart-box-outline"></ha-icon>
            <ha-icon id="bt-set"   icon="mdi:cog"></ha-icon>
          </span>
        </div>
        <div class="body">
          <div class="ring">
            <svg width="104" height="104" viewBox="0 0 104 104">
              <circle cx="52" cy="52" r="46" fill="none" stroke="rgba(255,255,255,0.10)" stroke-width="8"/>
              <circle id="ring-fg" cx="52" cy="52" r="46" fill="none" stroke="#4caf50" stroke-width="8"
                      stroke-linecap="round" stroke-dasharray="289" stroke-dashoffset="289"/>
            </svg>
            <div class="pct" id="pct">—</div>
          </div>
          <div class="info">
            <div class="row"><span class="lbl">Stato</span><span class="val" id="stato"><span class="statebadge battery">—</span></span></div>
            <div class="row"><span class="lbl">Tempo</span><span class="val" id="tempo">—</span></div>
            <div class="row"><span class="lbl">Soglie</span><span class="val" id="soglie">—</span></div>
            <div class="row"><span class="lbl">Auto-ricarica</span><span class="val" id="auto">—</span></div>
          </div>
        </div>
        <div class="cycles">
          <div class="c"><div class="n" id="c-oggi">0</div><div class="t">Oggi</div></div>
          <div class="c"><div class="n" id="c-mese">0</div><div class="t">Mese</div></div>
          <div class="c"><div class="n" id="c-anno">0</div><div class="t">Anno</div></div>
          <div class="c"><div class="n" id="c-tot">0</div><div class="t">Totali</div></div>
        </div>
      </div>`;
    this._q('#bt-stats').addEventListener('click', () => this._showStats());
    this._q('#bt-set').addEventListener('click', () => this._showSettings());
    this._update();
  }

  _update() {
    if (!this._ready || !this._hass) return;
    const st = this._hass.states[this._bat()];
    if (!st) {
      const pctEl = this._q('#pct');
      if (pctEl) pctEl.textContent = '?';
      const statoEl = this._q('#stato');
      if (statoEl) statoEl.innerHTML =
        `<span class="statebadge battery">Entità non trovata: ${ElettrodomesticoDispositivoCard._esc(this._bat())}</span>`;
      return;
    }
    const pct = parseFloat(st.state) || 0;
    const charging = this._a('stato_carica') === 'In ricarica';

    // Optional image: if image_on/off configured, show it instead of the ring
    const imgOn  = this._config.image_on  || this._a('image_on')  || '';
    const imgOff = this._config.image_off || this._a('image_off') || '';
    const imgSrc = (charging && imgOn) ? imgOn : imgOff;
    const ringWrap = this._q('.ring');
    let imgEl = this._q('#dev-img');
    if (imgSrc) {
      if (ringWrap) ringWrap.style.display = 'none';
      if (!imgEl) {
        imgEl = document.createElement('img');
        imgEl.id = 'dev-img';
        imgEl.style.cssText = 'width:96px;height:96px;object-fit:contain;flex:0 0 auto;';
        this._q('.body').insertBefore(imgEl, this._q('.info'));
      }
      imgEl.style.display = '';
      const resolved = new URL(imgSrc, document.baseURI).href;
      if (imgEl.src !== resolved) imgEl.src = imgSrc;
    } else {
      if (ringWrap) ringWrap.style.display = '';
      if (imgEl) imgEl.style.display = 'none';
    }

    // ring
    const circ = 289; // 2*pi*46
    this._q('#ring-fg').style.strokeDashoffset = String(circ - (circ * Math.min(100, Math.max(0, pct)) / 100));
    this._q('#ring-fg').style.stroke = charging ? '#4caf50' : (pct <= (parseFloat(this._a('soglia_avvio'))||20) ? '#f44336' : '#3b82f6');
    this._q('#pct').textContent = `${Math.round(pct)}%`;

    const badge = charging
      ? `<span class="statebadge charging">⚡ In ricarica</span>`
      : `<span class="statebadge battery">🔋 A batteria</span>`;
    this._q('#stato').innerHTML = badge;
    this._q('#tempo').textContent = charging ? this._a('tempo_in_carica','—') : this._a('tempo_a_batteria','—');
    this._q('#soglie').textContent = `${this._a('soglia_avvio','?')}% → ${this._a('soglia_stop','?')}%`;
    this._q('#auto').textContent = this._a('auto_attivo') ? 'Attiva' : 'Disattivata';

    this._q('#c-oggi').textContent = this._a('ricariche_oggi', 0);
    this._q('#c-mese').textContent = this._a('ricariche_mese', 0);
    this._q('#c-anno').textContent = this._a('ricariche_anno', 0);
    this._q('#c-tot').textContent  = this._a('ricariche_totali', 0);

    const nm = this._config.name || this._a('friendly_name');
    if (nm) this._q('#nm').textContent = nm;
  }

  _popup(title, content) {
    this.dispatchEvent(new CustomEvent('ll-custom', {
      bubbles: true, composed: true,
      detail: { action: 'fire-dom-event', browser_mod: { service: 'browser_mod.popup',
        data: { title, style: '--popup-background-color: var(--card-background-color); --dialog-backdrop-filter: blur(2em) brightness(0.75);', content } } },
    }));
  }


  _showStats() {
    const s = this._slot;
    const mid = this._bat();
    const I = (attr, clickEntity) => ({ entity: mid, attr, integer: true, clickEntity });
    const rowsNow = [
      { cells: [{text:'Oggi'},   I('ricariche_oggi',   `sensor.cicli_ricarica_oggi_${this._slot}`)] },
      { cells: [{text:'Mese'},   I('ricariche_mese',   `sensor.cicli_ricarica_mese_${this._slot}`)] },
      { cells: [{text:'Anno'},   I('ricariche_anno',   `sensor.cicli_ricarica_anno_${this._slot}`)] },
      { cells: [{text:'Totali'}, I('ricariche_totali', `sensor.cicli_ricarica_totali_${this._slot}`)] },
    ];
    const rowsPrev = [
      { cells: [{text:'Ieri'},       I('ricariche_ieri')] },
      { cells: [{text:'Mese Prec.'}, I('ricariche_mese_prec')] },
      { cells: [{text:'Anno Prec.'}, I('ricariche_anno_prec')] },
    ];
    this._popup('Statistiche Ricariche', {
      type: 'vertical-stack',
      cards: [
        { type: 'custom:em-stat-table', title: '🔋 Stato Attuale',
          headers: ['', 'Valore'],
          rows: [
            { cells: [{text:'Batteria'},        {state:mid, integer:true, suffix:'%'}] },
            { cells: [{text:'Stato'},           {entity:mid, attr:'stato_carica', raw:true, fallback:'—'}] },
            { cells: [{text:'Tempo in Carica'}, {entity:mid, attr:'tempo_in_carica', raw:true, fallback:'—'}] },
            { cells: [{text:'Tempo a Batteria'},{entity:mid, attr:'tempo_a_batteria', raw:true, fallback:'—'}] },
          ],
        },
        { type: 'custom:em-stat-table', title: '📊 Periodo Corrente',
          headers: ['Periodo','Ricariche'], rows: rowsNow },
        { type: 'custom:em-stat-table', title: '🗓️ Periodi Precedenti',
          headers: ['Periodo','Ricariche'], rows: rowsPrev },
      ],
    });
  }

  _showSettings() {
    const s = this._slot;
    const mid = this._bat();
    this._popup('Impostazioni Dispositivo', {
      type: 'entities',
      entities: [
        { type: 'divider' },
        { entity: `text.nome_dispositivo_${s}`, name: 'Nome', icon: 'mdi:rename-box' },
        { type: 'divider' },
        { entity: `switch.carica_dispositivo_${s}`,         name: 'Presa di Ricarica', icon: 'mdi:power-plug' },
        { entity: `switch.ricarica_auto_dispositivo_${s}`,  name: 'Ricarica Automatica', icon: 'mdi:battery-sync' },
        { type: 'divider' },
        { entity: `number.soglia_avvio_carica_${s}`, name: 'Soglia Avvio Carica', icon: 'mdi:battery-10' },
        { entity: `number.soglia_stop_carica_${s}`,  name: 'Soglia Stop Carica',  icon: 'mdi:battery-charging-100' },
        { type: 'divider' },
        {
          entity: `switch.notifica_push_elettrodomestici_${s}`,
          name: 'Notifiche', icon: 'mdi:bell',
          type: 'custom:multiple-entity-row', show_state: false,
          entities: [
            { entity: `switch.notifica_google_elettrodomestici_${s}`,   name: 'GOOGLE',   toggle: true },
            { entity: `switch.notifica_alexa_elettrodomestici_${s}`,    name: 'ALEXA',    toggle: true },
            { entity: `switch.notifica_whatsapp_elettrodomestici_${s}`, name: 'WHATSAPP', toggle: true },
            { entity: `switch.notifica_push_elettrodomestici_${s}`,     name: 'PUSH',     toggle: true },
          ],
        },
        { type: 'divider' },
        { entity: `button.manutenzione_elettrodomestici_${s}`,   name: 'Registra Manutenzione', icon: 'mdi:wrench-clock' },
        { entity: `button.reset_contatori_elettrodomestici_${s}`, name: 'Reset Contatori', icon: 'mdi:restore' },
        { type: 'attribute', entity: this._bat(), attribute: 'reset_date', name: 'Ultimo Reset', icon: 'mdi:history' },
        { type: 'divider' },
      ],
    });
  }

  getCardSize() { return 4; }
  static getStubConfig() { return { slot: 301, name: 'Dispositivo' }; }
}

if (!customElements.get('elettrodomestico-dispositivo-card')) {
  customElements.define('elettrodomestico-dispositivo-card', ElettrodomesticoDispositivoCard);
}
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'elettrodomestico-dispositivo-card',
  name: 'Elettrodomestico — Dispositivo (Batteria)',
  description: 'Card per la gestione ricarica batterie (preset dispositivo).',
});
console.info('%c ELETTRODOMESTICO-DISPOSITIVO-CARD %c v6.0.4 ', 'background:#00d4ff;color:#000;font-weight:700', 'background:#222;color:#fff');
