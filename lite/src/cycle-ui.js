import {coolingResults} from './cooling-ui.js';

/** Inspector fields for the bounded component cycle models. */
export const COMPONENT_FIELDS = {
  pump: [
    {key:'riseBar',label:'Druckerhöhung',unit:'bar',min:0.01,max:150,step:0.01},
    {key:'efficiency',label:'Pumpenwirkungsgrad',unit:'–',min:0.05,max:1,step:0.01},
  ],
  regen: [
    {key:'heatKW',label:'Wärmeaufnahme',unit:'kW',min:0,max:5000,step:1},
    {key:'dropBar',label:'Druckverlust',unit:'bar',min:0,max:100,step:0.1},
    {key:'cpJkgK',label:'Spez. Wärmekapazität',unit:'J/(kg·K)',min:100,max:10000,step:50},
  ],
  shaft: [
    {key:'efficiency',label:'Mechanischer Wirkungsgrad',unit:'–',min:0.05,max:1,step:0.01},
    {key:'rpm',label:'Drehzahl',unit:'min⁻¹',min:100,max:200000,step:100},
    {key:'motorKW',label:'Externe Antriebsleistung',unit:'kW',min:0,max:10000,step:1},
  ],
  gasSource: [
    {key:'pressureBar',label:'Eintrittsdruck',unit:'bar',min:0.1,max:200,step:0.1},
    {key:'temperatureK',label:'Gastemperatur',unit:'K',min:200,max:2000,step:10},
    {key:'massFlowKgS',label:'Zusätzlicher Gasmassenstrom',unit:'kg/s',min:0.001,max:10,step:0.001},
    {key:'cpJkgK',label:'Spez. Wärmekapazität',unit:'J/(kg·K)',min:500,max:10000,step:50},
    {key:'gamma',label:'Isentropenexponent γ',unit:'–',min:1.05,max:1.67,step:0.01},
  ],
  turbine: [
    {key:'outletBar',label:'Austrittsdruck',unit:'bar',min:0.01,max:200,step:0.01},
    {key:'efficiency',label:'Isentroper Wirkungsgrad',unit:'–',min:0.05,max:1,step:0.01},
  ],
  exhaust: [
    {key:'exitBar',label:'Düsenaustrittsdruck',unit:'bar',min:0.001,max:200,step:0.001},
    {key:'efficiency',label:'Düsenwirkungsgrad',unit:'–',min:0.05,max:1,step:0.01},
  ],
};

export const COMPONENT_NOTES = {
  pump: 'Inkompressible Druckarbeit bei vorgegebener Druckerhöhung und konstanten Stoffwerten. Der Wirkungsgrad bestimmt den Wellenleistungsbedarf; keine Pumpenkennlinie oder Kavitationsberechnung.',
  regen: 'Kanalmodell: Geometrie und Brennstoffmassenstrom werden aus dem Entwurf übernommen; thermische Profile und Druckverlust werden berechnet. Altes Vorgabemodell: Wärmeaufnahme, Druckverlust und cp bleiben Eingaben. Die CEA-Thermochemie wird nicht mit der Kühlung rückgekoppelt.',
  shaft: 'Die Welle vergleicht Pumpenbedarf mit Turbinenleistung nach mechanischem Wirkungsgrad und externer Antriebsleistung. Die externe Leistung wird als an der Welle verfügbar vorgegeben. Drehzahl dient der Drehmomentberechnung; keine Drehzahldynamik.',
  gasSource: 'Separat vorgegebener Heißgasstrom mit konstantem cp und γ. Zusätzlicher Massenstrom zählt zum Systemverbrauch. Keine berechnete Gasgeneratorchemie und keine automatische Aufteilung aus den Hauptversorgungspfaden.',
  turbine: 'Idealgas-Expansion zwischen vorgegebenen Drücken mit konstantem cp und γ. Der isentrope Wirkungsgrad bestimmt Temperaturabfall und Leistung; keine Turbinenkennlinie.',
  exhaust: 'Separate Abgasdüse mit vorgegebenem Austrittsdruck und Wirkungsgrad. Impuls- und Druckschub ergänzen den Hauptschub. Keine Konturoptimierung oder Ablösungsberechnung.',
};

/** Render the cycle ledger. labels optionally maps node IDs to project labels. */
export function cycleResults(result, esc, fmt, labels = {}, coolingOptions = {}) {
  const c = result?.cycle;
  if (!result?.ok || !c) return '';
  const pumps = c.pumps || [], shafts = c.shafts || [], turbines = c.turbines || [], cooling = c.cooling || [];
  const legacyCooling = cooling.filter(r => r.mode !== 'channels');
  if (!pumps.length && !shafts.length && !turbines.length && !cooling.length && !c.auxiliary) return '';
  const name = id => esc(labels[id] || id || 'Komponente');
  const val = (n, digits = 2) => Number.isFinite(n) ? esc(fmt(n, digits)) : '—';
  const row = (label, n, unit, digits = 2) => `<div><dt>${label}</dt><dd>${val(n, digits)} ${unit}</dd></div>`;
  const card = (id, kind, body) => `<article class="cycle-component"><div class="cycle-component-header"><h3>${name(id)}</h3><span class="eyebrow">${kind}</span></div><dl>${body}</dl></article>`;
  let html = `<section class="cycle-results" aria-label="Cycle- und Leistungsbilanz"><div class="eyebrow">CYCLE / KOMPONENTENBILANZ</div><h2>Leistung im Zusammenhang.</h2><p class="help-text">Vorgegebene Komponentenmodelle am Zielbetriebspunkt. Wellenleistung und Versorgungsdruck werden getrennt geprüft.</p>`;

  for (const s of shafts) {
    const enough = s.feasible === true;
    const balance = Number.isFinite(s.balanceKW) ? Math.abs(s.balanceKW) : NaN;
    const ratio = Number.isFinite(s.availablePowerKW) && Number.isFinite(s.requiredPowerKW) && s.requiredPowerKW > 0
      ? Math.max(0, Math.min(100, s.availablePowerKW / s.requiredPowerKW * 100)) : 0;
    html += `<div class="cycle-ledger"><div class="cycle-ledger-heading"><h3><i class="legend-dot mechanical"></i>${name(s.nodeId)}</h3><span class="badge ${enough ? 'success' : 'danger'}">${enough ? 'LEISTUNG AUSREICHEND' : 'LEISTUNG FEHLT'}</span></div>
      <div class="cycle-ledger-row"><span>Pumpenbedarf</span><strong>${val(s.requiredPowerKW)} kW</strong></div>
      <div class="cycle-ledger-row"><span>Turbinenleistung, vor Wellenverlust</span><strong>${val(s.turbinePowerKW)} kW</strong></div>
      <div class="cycle-ledger-row"><span>Externer Antrieb, an der Welle</span><strong>${val(s.motorKW)} kW</strong></div>
      <div class="cycle-ledger-row"><span>Verfügbar, nach Wellenverlust</span><strong>${val(s.availablePowerKW)} kW</strong><small>Mechanischer Wirkungsgrad: ${val(s.efficiency * 100, 1)} % auf die Turbinenleistung.</small></div>
      <div class="cycle-ledger-row balance"><span>${enough ? 'Leistungsreserve' : 'Leistungsdefizit'}</span><strong class="${enough ? 'success' : 'danger'}">${val(balance)} kW</strong><small class="cycle-power-bar" aria-label="Verfügbare Leistung relativ zum Pumpenbedarf"><span style="width:${ratio}%"></span></small></div>
      <div class="cycle-ledger-row"><span>Drehzahl</span><strong>${val(s.rpm, 0)} min⁻¹</strong></div>
      <div class="cycle-ledger-row"><span>Drehmoment · Bedarf / verfügbar</span><strong>${val(s.requiredTorqueNm)} / ${val(s.availableTorqueNm)} N·m</strong></div></div>`;
  }

  if (pumps.length) html += `<div class="section-label">PUMPEN</div><div class="cycle-component-list">${pumps.map(p => card(p.nodeId, 'DRUCKARBEIT',
    row('Druckerhöhung', p.pressureRiseBar, 'bar') + row('Hydraulische Leistung', p.hydraulicPowerKW, 'kW') + row('Wellenbedarf', p.shaftPowerKW, 'kW') + row('Massenstrom', p.massFlowKgS, 'kg/s', 3) + `<div><dt>Welle</dt><dd>${name(p.shaftId)}</dd></div>`)).join('')}</div>`;

  if (turbines.length) html += `<div class="section-label">TURBINEN</div><div class="cycle-component-list">${turbines.map(t => card(t.nodeId, 'IDEALGAS-EXPANSION',
    row('Leistung vor Wellenverlust', t.powerKW, 'kW') + row('Eintrittsdruck', t.inletPressureBar, 'bar') + row('Austrittsdruck', t.outletPressureBar, 'bar') + row('Eintrittstemperatur', t.inletTemperatureK, 'K', 1) + row('Austrittstemperatur', t.outletTemperatureK, 'K', 1) + row('Massenstrom', t.massFlowKgS, 'kg/s', 3))).join('')}</div>`;

  if (legacyCooling.length) html += `<div class="section-label">WÄRMEAUFNAHME · VORGABEMODELL</div><div class="cycle-component-list">${legacyCooling.map(r => card(r.nodeId, 'VORGEGEBENER WÄRMESTROM',
    row('Wärmeaufnahme', r.heatKW, 'kW') + row('Druckverlust', r.dropBar, 'bar') + row('Eintrittstemperatur', r.inletTemperatureK, 'K', 1) + row('Austrittstemperatur', r.outletTemperatureK, 'K', 1) + row('Massenstrom', r.massFlowKgS, 'kg/s', 3))).join('')}</div>`;

  const a = c.auxiliary;
  if (a) {
    html += `<div class="section-label">SEPARATER HEISSGASPFAD</div>${card(a.exhaustId, 'ABGASDÜSE',
      row('Zusätzlicher Massenstrom', a.massFlowKgS, 'kg/s', 3) + row('Austrittsdruck', a.exitPressureBar, 'bar') + row('Austrittstemperatur', a.exitTemperatureK, 'K', 1) + row('Austrittsgeschwindigkeit', a.exitVelocityMS, 'm/s', 1) + row('Austrittsfläche', a.exitAreaM2 * 1e6, 'mm²', 1) + row('Zusätzlicher Schub', a.thrustN, 'N', 1))}
      <div class="cycle-system-summary"><div class="cycle-system-value"><span>Gesamtschub</span><strong>${val(a.systemThrustN / 1000)}<small>kN</small></strong><small>Haupttriebwerk + separate Abgasdüse</small></div><div class="cycle-system-value"><span>System-Isp</span><strong>${val(a.systemIspS, 1)}<small>s</small></strong><small>Mit zusätzlichem Heißgasmassenstrom</small></div></div>
      <div class="pressure-row"><span>Gesamtmassenstrom</span><strong>${val(a.totalMassFlowKgS, 3)} kg/s</strong></div>`;
  }
  html += `<p class="cycle-caveat">${shafts.length ? 'Eine Leistungsreserve ist kein gelöster Drehzahlgleichgewichtspunkt. ' : ''}${legacyCooling.length ? 'Im Vorgabemodell sind Wärmeaufnahme und cp Eingaben; Wandtemperatur und Kühlkanäle werden damit nicht ausgelegt. ' : ''}${a ? 'Der Heißgasstrom ist eine separate Randbedingung. Gasgeneratorchemie, Abzweige und vollständiger Cycle-Abschluss sind nicht gelöst. ' : ''}Keine Kennfeld-, Transienten- oder Lebensdauerbewertung.</p></section>`;
  html += coolingResults(result, esc, fmt, labels, coolingOptions);
  return html;
}
