/**
 * em-stat-table v6.0.4
 * Tabella statistiche stilata, renderizzata nel proprio shadow DOM
 * (immune alla sanitizzazione HTML della markdown card di HA).
 *
 * config: {
 *   type: 'custom:em-stat-table',
 *   title: '📊 Periodo Corrente',
 *   headers: ['Periodo','Cicli','Tempo','€ Tot'],
 *   rows: [ { label:'Oggi', entity:'sensor.x', attrs:['cicli_oggi', ...], states:[...] } ]
 * }
 *
 * Each row cell is resolved at render time from either:
 *   - {attr: 'attr_name', entity: 'sensor.x'} → state_attr
 *   - {state: 'sensor.x'} → states
 *   - {state: 'sensor.x', lastPeriod: true} → state_attr(.,'last_period')
 *   - {text: 'literal'} → literal text
 *   - {suffix: ' kWh'} appended
 */
class EmStatTable extends HTMLElement {
  constructor() { super(); this.attachShadow({ mode: 'open' }); }

  setConfig(cfg) {
    this._cfg = cfg;
    this._built = false;
    this._render();
  }

  set hass(h) {
    this._hass = h;
    if (!this._built) this._render();
    else this._updateValues();
  }

  _resolve(cell) {
    if (!this._hass) return '—';
    if (cell.text !== undefined) return cell.text;
    let v;
    if (cell.sum !== undefined) {
      // Sum multiple attributes of the same entity
      let tot = 0;
      for (const a of cell.sum) {
        const x = parseFloat(this._hass.states[cell.entity]?.attributes?.[a]);
        if (!isNaN(x)) tot += x;
      }
      v = tot;
    } else if (cell.attr !== undefined) {
      v = this._hass.states[cell.entity]?.attributes?.[cell.attr];
    } else if (cell.lastPeriod) {
      v = this._hass.states[cell.entity]?.attributes?.last_period;
    } else if (cell.state !== undefined) {
      v = this._hass.states[cell.state]?.state;
    }
    // Track whether the source existed at all (vs. existing but empty/zero).
    let _found = true;
    if (cell.attr !== undefined) {
      const attrs = this._hass.states[cell.entity]?.attributes;
      _found = attrs !== undefined && cell.attr in attrs;
    } else if (cell.lastPeriod) {
      const attrs = this._hass.states[cell.entity]?.attributes;
      _found = attrs !== undefined && 'last_period' in attrs;
    } else if (cell.state !== undefined) {
      _found = this._hass.states[cell.state] !== undefined;
    }
    if (v === undefined || v === null || v === '') {
      // Debug mode: surface only TRULY missing entities/attributes (naming
      // mismatches). An attribute that exists but is empty/zero is legitimate
      // (e.g. 'zona_attiva' is "" when no zone is running) → normal fallback.
      if (this._cfg?.debug && !_found) {
        const ref = cell.entity || cell.state || '?';
        const what = cell.attr ? `${ref}@${cell.attr}` : (cell.lastPeriod ? `${ref}@last_period` : ref);
        return `⚠️${what}`;
      }
      v = (cell.fallback ?? '—');
    }
    // Number formatting: Italian locale (comma decimal), 2 decimals by default.
    // - cell.euro    → always 2 decimals
    // - cell.integer → no decimals (e.g. cycle counts)
    // - cell.decimals→ explicit decimal count
    // - cell.raw     → leave as-is (strings like "1h 4m", "Fermo", dates)
    // Otherwise: if the value is numeric, format to 2 decimals with comma.
    if (!cell.raw && cell.text === undefined) {
      const n = parseFloat(v);
      if (!isNaN(n) && isFinite(n) && /^-?\d*[.,]?\d+$/.test(String(v).trim())) {
        let dec = 2;
        if (cell.integer) dec = 0;
        else if (cell.euro) dec = 2;
        else if (cell.decimals !== undefined) dec = cell.decimals;
        v = n.toLocaleString('it-IT', { minimumFractionDigits: dec, maximumFractionDigits: dec });
      }
    }
    return `${v}${cell.suffix || ''}`;
  }

  _render() {
    if (!this._cfg || !this._hass) return;
    const { title, headers = [], rows = [] } = this._cfg;
    const th = headers.map((h, i) =>
      `<th class="${i === 0 ? 'first' : ''}${i === headers.length - 1 ? ' last' : ''}">${h}</th>`).join('');
    const body = rows.map((r, ri) => {
      const cells = r.cells.map((c, i) => {
        const val = i === 0 ? (r.label ?? this._resolve(c)) : this._resolve(c);
        // Mark dynamic cells (everything resolved from state) for in-place updates
        const dyn = (i === 0 && r.label !== undefined) ? '' : ` data-r="${ri}" data-c="${i}"`;
        return `<td class="${i === 0 ? 'first' : ''}"${dyn}>${val}</td>`;
      }).join('');
      return `<tr>${cells}</tr>`;
    }).join('');
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; margin: 6px 0 12px; }
        .ttl { font-weight:600; font-size:14px; margin:0 0 7px 2px; color:var(--primary-text-color,#e2e8f0); }
        .wrap { overflow-x:auto; -webkit-overflow-scrolling:touch; border-radius:10px;
                box-shadow:0 1px 4px rgba(0,0,0,0.18); }
        table { width:100%; border-collapse:collapse; }
        th { background:var(--primary-color,#03a9f4); color:#fff; font-weight:600;
             padding:8px 9px; text-align:right; white-space:nowrap; font-size:12.5px;
             position:sticky; top:0; }
        th.first { text-align:left; position:sticky; left:0; z-index:2; }
        td { padding:8px 9px; text-align:right; white-space:nowrap; font-size:12.5px;
             color:var(--primary-text-color,#e2e8f0);
             border-bottom:1px solid rgba(127,127,127,0.16); cursor:pointer; }
        td.first { text-align:left; color:var(--secondary-text-color,#94a3b8); font-weight:600;
                   position:sticky; left:0; background:var(--card-background-color,#1c1c1c); z-index:1;
                   cursor:default; }
        tr:nth-child(even) td { background:rgba(127,127,127,0.06); }
        tr:nth-child(even) td.first { background:var(--card-background-color,#1c1c1c); }
        tr:last-child td { border-bottom:none; }
        td:hover:not(.first) { background:rgba(3,169,244,0.14); }
        @media (max-width: 500px) {
          th, td { padding:6px 7px; font-size:11.5px; }
        }
      </style>
      ${title ? `<div class="ttl">${title}</div>` : ''}
      <div class="wrap"><table><thead><tr>${th}</tr></thead><tbody>${body}</tbody></table></div>`;
    this._built = true;
    this._wireClicks();
  }

  _updateValues() {
    // Update only dynamic cell text — preserves scroll position and DOM.
    if (!this._built) return;
    const { rows = [] } = this._cfg;
    this.shadowRoot.querySelectorAll('td[data-r]').forEach(td => {
      const ri = +td.dataset.r, ci = +td.dataset.c;
      const cell = rows[ri]?.cells[ci];
      if (cell) {
        const v = this._resolve(cell);
        if (td.textContent !== v) td.textContent = v;
      }
    });
  }

  _wireClicks() {
    // Clicking a data cell opens the native HA more-info for the underlying entity.
    const { rows = [] } = this._cfg;
    this.shadowRoot.querySelectorAll('td[data-r]').forEach(td => {
      const ri = +td.dataset.r, ci = +td.dataset.c;
      const cell = rows[ri]?.cells[ci];
      const eid = cell?.clickEntity || cell?.entity || cell?.state;
      if (!eid || cell?.noClick) return;
      td.addEventListener('click', () => {
        this.dispatchEvent(new CustomEvent('hass-more-info', {
          bubbles: true, composed: true, detail: { entityId: eid },
        }));
      });
    });
  }

  getCardSize() { return Math.max(1, (this._cfg?.rows?.length || 3)); }
}

if (!customElements.get('em-stat-table')) {
  customElements.define('em-stat-table', EmStatTable);
}
console.info('%c EM-STAT-TABLE %c v6.0.4 ', 'background:#00d4ff;color:#000;font-weight:700', 'background:#222;color:#fff');
