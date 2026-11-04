export {CHANNEL_FIELDS, CHANNEL_DEFAULTS} from './cooling-config.js';

export const CHANNEL_NOTE = 'Kanalgeometrie entlang der aktuellen Kammer-/Düsenkontur. Brennstoffmassenstrom und Eintrittszustand kommen aus dem Versorgungspfad. Wärmeaufnahme, Druckverlust sowie heiße/kalte Wandtemperatur werden stationsweise berechnet. Die eingegebene Temperaturgrenze ist ein Vergleichswert, kein qualifizierter Werkstoffnachweis.';

const VIEWS = {
  temperature:{label:'Temperaturen',unit:'K',series:[['hotWallTemperatureK','Heiße Wand','#f0ab73'],['coldWallTemperatureK','Kalte Wand','#bca2e9'],['coolantTemperatureK','Kühlmittel','#70d0df']],scale:1},
  heatflux:{label:'Wärmestrom',unit:'MW/m²',series:[['heatFluxWm2','Wärmestromdichte','#f0ab73']],scale:1e-6},
  pressure:{label:'Druck',unit:'bar',series:[['coolantPressureBar','Statischer Kühlmitteldruck','#70d0df']],scale:1},
};

function selectedIndex(stations, requested) {
  if (Number.isInteger(requested) && requested >= 0 && requested < stations.length) return requested;
  let selected = 0;
  for (let i=1;i<stations.length;i++) if (stations[i].hotWallTemperatureK > stations[selected].hotWallTemperatureK) selected=i;
  return selected;
}

function chart(entry, view, selected, esc, fmt) {
  const spec=VIEWS[view],stations=entry.stations;
  const left=58,right=535,top=35,bottom=246;
  const minX=Math.min(...stations.map(s=>s.xM)),maxX=Math.max(...stations.map(s=>s.xM));
  const values=stations.flatMap(s=>spec.series.map(([key])=>s[key]*spec.scale)).filter(Number.isFinite);
  const limit=entry.maxHotWallTemperatureK+entry.wallMarginK;
  if(view==='temperature'&&Number.isFinite(limit))values.push(limit);
  const rawMin=Math.min(...values),rawMax=Math.max(...values);
  const range=Math.max(rawMax-rawMin,Math.abs(rawMax)*0.05,1);
  const minY=Math.max(0,rawMin-range*0.08),maxY=rawMax+range*0.12;
  const x=v=>left+(v-minX)/Math.max(maxX-minX,0.000001)*(right-left);
  const y=v=>bottom-(v-minY)/Math.max(maxY-minY,0.000001)*(bottom-top);
  const coord=v=>Number.isFinite(v)?v.toFixed(2):'0';
  const value=(v,d=1)=>esc(fmt(v,d));
  let svg=`<svg class="cooling-chart" viewBox="0 0 560 290" role="img" aria-label="${esc(spec.label)} entlang der Kammer- und Düsenachse; markierte Station ${selected+1}"><text class="axis-label" x="${left}" y="17">${esc(spec.unit)}</text>`;
  for(let i=0;i<=4;i++){
    const v=minY+(maxY-minY)*i/4,py=y(v);
    svg+=`<line class="plot-grid" x1="${left}" x2="${right}" y1="${coord(py)}" y2="${coord(py)}"/><text class="axis-tick" x="${left-8}" y="${coord(py+4)}" text-anchor="end">${value(v,view==='temperature'?0:1)}</text>`;
  }
  for(let i=0;i<=4;i++){
    const v=minX+(maxX-minX)*i/4,px=x(v);
    svg+=`<text class="axis-tick" x="${coord(px)}" y="264" text-anchor="middle">${value(v*1000,0)}</text>`;
  }
  svg+=`<text class="axis-label" x="${right}" y="283" text-anchor="end">Axiale Position x [mm]</text>`;
  if(Number.isFinite(entry.throatX)&&entry.throatX>=minX&&entry.throatX<=maxX){
    const tx=x(entry.throatX);
    svg+=`<line x1="${coord(tx)}" x2="${coord(tx)}" y1="${top}" y2="${bottom}" stroke="#788d99" stroke-dasharray="5 5" opacity=".65"/><text class="throat-label" x="${coord(tx)}" y="28" text-anchor="middle">Düsenhals</text>`;
  }
  if(view==='temperature'&&Number.isFinite(limit))svg+=`<line x1="${left}" x2="${right}" y1="${coord(y(limit))}" y2="${coord(y(limit))}" stroke="#f1a193" stroke-width="1.3" stroke-dasharray="6 5"/>`;
  svg+=`<line class="station-marker" x1="${coord(x(stations[selected].xM))}" x2="${coord(x(stations[selected].xM))}" y1="${top}" y2="${bottom}"/>`;
  for(const [key,label,color] of spec.series){
    let started=false;
    const d=stations.map(s=>{const v=s[key]*spec.scale;if(!Number.isFinite(v)){started=false;return '';}const p=`${started?'L':'M'}${coord(x(s.xM))},${coord(y(v))}`;started=true;return p;}).join(' ');
    svg+=`<path d="${d}" fill="none" stroke="${color}" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"/>`;
    const active=stations[selected][key]*spec.scale;
    if(Number.isFinite(active))svg+=`<circle cx="${coord(x(stations[selected].xM))}" cy="${coord(y(active))}" r="4" fill="${color}" stroke="#11191d" stroke-width="1.5"><title>${esc(label)}: ${value(active)} ${esc(spec.unit)}</title></circle>`;
  }
  return svg+'</svg>';
}

/** options is a per-node map: { [nodeId]: { view, station } }. */
export function coolingResults(result,esc,fmt,labels={},options={}) {
  if(!result?.ok)return '';
  const entries=(result.cycle?.cooling||[]).filter(c=>c.mode==='channels'&&Array.isArray(c.stations)&&c.stations.length);
  const value=(n,d=1)=>Number.isFinite(n)?esc(fmt(n,d)):'—';
  return entries.map(c=>{
    const id=esc(c.nodeId),name=esc(labels[c.nodeId]||c.nodeId),opts=options[c.nodeId]||{};
    const view=Object.hasOwn(VIEWS,opts.view)?opts.view:'temperature',spec=VIEWS[view],index=selectedIndex(c.stations,opts.station),s=c.stations[index];
    const limit=c.maxHotWallTemperatureK+c.wallMarginK;
    const limitPass=Number.isFinite(c.wallMarginK)&&c.wallMarginK>=0;
    const badge=limitPass?'UNTER EINGEGEBENER GRENZE':'WANDGRENZE ÜBERSCHRITTEN';
    const metric=(label,n,unit,d=1,extra='')=>`<div class="cooling-metric"><span>${label}</span><strong>${value(n,d)}<small>${unit}</small></strong>${extra?`<small>${extra}</small>`:''}</div>`;
    const stationValue=(label,n,unit,d=1)=>`<div><span>${label}</span><strong>${value(n,d)} ${unit}</strong></div>`;
    return `<section class="cooling-results" aria-label="Kanalkühlung ${name}"><div class="cooling-heading"><div><div class="eyebrow">REGENERATIV / KANALMODELL</div><h2>${name}</h2></div><span class="badge ${limitPass?'success':'danger'}">${badge}</span></div>
      <p class="help-text">Kammer- und Düsenkontur aus diesem Entwurf. Brennstoff ${c.flowDirection==='co'?'im Gleichstrom →':'im Gegenstrom ←'}. Kühlstrecke: ${value((c.coolingStart??0)*100,0)}–${value((c.coolingEnd??1)*100,0)} % der Kontur. ${c.fullCoverage===false?'Ungekühlte Bereiche sind nicht bewertet.':''} Die Diagramme sind in Gasströmungsrichtung angeordnet.</p>
      <div class="cooling-metrics">${metric('Maximale heiße Wand',c.maxHotWallTemperatureK,'K',0,`Vorgegebene Grenze: ${value(limit,0)} K`)}${metric('Maximale Wärmestromdichte',c.maxHeatFluxWm2*1e-6,'MW/m²',2)}${metric('Berechnete Wärmeaufnahme',c.heatKW,'kW',1)}${metric('Berechneter Druckverlust',c.dropBar,'bar',2)}${metric('Kühlmittel am Austritt',c.outletTemperatureK,'K',1)}${metric('Abstand zur Wandgrenze',c.wallMarginK,'K',0,limitPass?'Vergleich innerhalb des Modells':'Eingegebene Grenze wird überschritten')}</div>
      <div class="cooling-chart-shell"><div class="cooling-chart-toolbar"><span>AXIALES PROFIL · ${c.stations.length} PROFILPUNKTE</span><div class="cooling-chart-options" role="group" aria-label="Diagrammgröße">${Object.entries(VIEWS).map(([key,v])=>`<button type="button" data-cooling-view="${key}" data-cooling-node="${id}" aria-pressed="${view===key}">${v.label}</button>`).join('')}</div></div>${chart(c,view,index,esc,fmt)}<div class="cooling-chart-legend">${spec.series.map(([key,label,color])=>`<span style="color:${color}"><i></i>${label}</span>`).join('')}${view==='temperature'?'<span class="limit"><i></i>Eingegebene Wandgrenze</span>':''}</div></div>
      <div class="cooling-station-controls"><label><span>Station untersuchen</span><select data-cooling-station="${id}" aria-label="Station für ${name}">${c.stations.map((p,i)=>`<option value="${i}" ${index===i?'selected':''}>${String(i+1).padStart(3,'0')} · x = ${value(p.xM*1000,1)} mm</option>`).join('')}</select></label></div>
      <div class="cooling-station-detail"><div class="section-label">STATION ${index+1} / ${c.stations.length} · x = ${value(s.xM*1000,1)} mm</div><div class="cooling-station-grid">${stationValue('Heiße Wand',s.hotWallTemperatureK,'K')}${stationValue('Kalte Wand',s.coldWallTemperatureK,'K')}${stationValue('Kühlmittel',s.coolantTemperatureK,'K')}${stationValue('Statischer Kühlmitteldruck',s.coolantPressureBar,'bar',2)}${stationValue('Wärmestromdichte',s.heatFluxWm2*1e-6,'MW/m²',2)}${stationValue('Lokale Kanalbreite',s.channelWidthMm,'mm',2)}${stationValue('Gas-HTC',s.gasHTCWm2K/1000,'kW/(m²·K)',2)}${stationValue('Kühlmittel-HTC',s.coolantHTCWm2K/1000,'kW/(m²·K)',2)}${stationValue('Kühlmittelgeschwindigkeit',s.velocityMS,'m/s',2)}${stationValue('Reynolds-Zahl',s.reynolds,'',0)}</div></div>
      <details><summary>Alle Kühlstationen</summary><div class="table-scroll"><table class="cooling-table"><thead><tr><th>Station</th><th>x [mm]</th><th>Wand heiß [K]</th><th>Wand kalt [K]</th><th>Kühlmittel [K]</th><th>p stat. [bar]</th><th>q [MW/m²]</th><th>Breite [mm]</th></tr></thead><tbody>${c.stations.map((p,i)=>`<tr class="${i===index?'selected':''}"><td><button type="button" data-cooling-index="${i}" data-cooling-node="${id}" aria-label="Station ${i+1} untersuchen">${i+1} ↗</button></td><td>${value(p.xM*1000,1)}</td><td>${value(p.hotWallTemperatureK,1)}</td><td>${value(p.coldWallTemperatureK,1)}</td><td>${value(p.coolantTemperatureK,1)}</td><td>${value(p.coolantPressureBar,2)}</td><td>${value(p.heatFluxWm2*1e-6,2)}</td><td>${value(p.channelWidthMm,2)}</td></tr>`).join('')}</tbody></table></div></details>
      <div class="dialog-actions"><button class="button" data-action="cooling-csv" data-cooling-node="${id}">Kühlstationen als CSV</button></div>
      <p class="cooling-caption">${Number.isFinite(c.energyResidualW)?`Energieresiduum: ${value(c.energyResidualW,3)} W. `:''}Die Profilpunkte umfassen die vorgegebenen axialen Unterteilungen, Konturstützstellen und zusätzliche Wandbewertungen an den Zellrändern. Randpunkte addieren keine Wärme zur Bilanz. Die lokale Kanalbreite folgt dem eingegebenen Anteil der Umfangsteilung. Die sichtbare Wandgrenze ist eine Entwurfsvorgabe, keine geprüfte Werkstoffzulässigkeit.</p>
      <p class="cycle-caveat">Berechnete thermische Modellwerte, keine zertifizierte Kühlung. Korrelationen und Stoffannahmen begrenzen die Aussage; keine Wandfestigkeit, Lebensdauer, Phasenwechsel- oder Verkokungsbewertung. Die Hauptthermochemie wird durch diese Wärmeentnahme nicht neu gekoppelt.</p></section>`;
  }).join('');
}
