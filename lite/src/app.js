import {createProject,compactFeedlines,clone,History,parseProject,fingerprint,TYPES,DEFAULT_PARAMS,TEMPLATES,createTemplate} from './state.js';
import {renderEngine} from './engine-ui.js';
import {GraphEditor} from './graph.js';
import {loadThermo} from './physics.js';
import {loadCoolingData} from './cooling.js';
import {CHANNEL_FIELDS,CHANNEL_DEFAULTS} from './cooling-config.js';
import {coolingResults} from './cooling-ui.js';
import {cycleResults,COMPONENT_FIELDS,COMPONENT_NOTES} from './cycle-ui.js';

const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=(n,d=2)=>Number.isFinite(n)?n.toLocaleString('de-DE',{maximumFractionDigits:d,minimumFractionDigits:d}):'—';
const STORE='astroforge-lite-project-v1';
const uid=()=>typeof crypto.randomUUID==='function'?crypto.randomUUID():'n-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,12);
let project=compactFeedlines(createProject()),storageWarning=false;
try{const saved=localStorage.getItem(STORE);if(saved)project=parseProject(saved);}catch{storageWarning=true;}
let history=new History(project),selectedId='design',section=null,result=null,resultKey=null,thermo=null,coolingData=null,worker=null,jobId=0,running=false,toastTimer;
const invalidDrafts=new Map();
let coolingViews={};
const draftKey=(id,scope,key)=>`${scope==='design'?'design':id}:${scope}:${key}`;
const stale=()=>!!result&&(invalidDrafts.size>0||resultKey!==fingerprint(project));
const graph=new GraphEditor($('#canvas'),{
 onSelect:id=>{selectedId=id;renderInspector();renderGraph();if(innerWidth<900)setPanel('inspector');},
 onMove:(id,x,y)=>mutate(p=>{const n=p.nodes.find(n=>n.id===id);if(n){n.x=x;n.y=y;}},false),
 onConnect:(from,to)=>connect(from,to),
 onSection:s=>{section=s;setPanel('canvas');render();},
 edgeContent:edge=>feedlinePanel(edge),
 onDeleteEdge:id=>mutate(p=>p.edges=p.edges.filter(e=>e.id!==id)),
});
function toast(message){clearTimeout(toastTimer);$('#toast').textContent=message;$('#toast').hidden=false;toastTimer=setTimeout(()=>$('#toast').hidden=true,4200);}
function persist(){try{localStorage.setItem(STORE,JSON.stringify(project));}catch{toast('Gerätespeicher nicht verfügbar. Bitte Projekt als Datei speichern.');}}
function mutate(fn,full=true){const p=clone(project);fn(p);if(JSON.stringify(p)===JSON.stringify(project))return;p.updatedAt=new Date().toISOString();project=history.commit(p);persist();if(full)render();else{renderGraph();renderResults();updateHistory();}}
function replaceProject(p){stopJob();coolingViews={};invalidDrafts.clear();project=p;history=new History(p);selectedId='design';section=null;result=null;resultKey=null;persist();render();setPanel('canvas');graph.fit();}
function setPanel(panel){document.body.dataset.mobilePanel=panel;document.querySelectorAll('[data-panel]').forEach(b=>b.setAttribute('aria-current',b.dataset.panel===panel?'page':'false'));if(panel==='canvas')requestAnimationFrame(()=>graph.fit());}
function updateHistory(){$('#undo').disabled=!history.past.length&&!invalidDrafts.size;$('#redo').disabled=!history.future.length;}
function renderGraph(){const host=$('#engine-section');$('.main-stage').dataset.engine=section==='cooling'?'true':'false';$('#fit').disabled=section==='cooling';host.hidden=section!=='cooling';if(section==='cooling')renderEngine(host,project,result,stale(),esc,num);graph.update(project,{selectedId,section,result,stale:stale()});}
function render(){
 $('#project-name').textContent=project.name;updateHistory();
 $('#breadcrumbs').innerHTML=`<button class="button button-quiet" data-section="root">Triebwerk</button>${section?`<span>/</span><strong>${section==='cooling'?'Kühlstrecke':section==='engine'?'Triebwerks-Section':section==='ox'?'Oxidatorversorgung':'Brennstoffversorgung'}</strong>`:'<span>/</span><strong>Systementwurf</strong>'}`;
 $('#tree').innerHTML='<button class="tree-item" data-section="engine">Triebwerks-Section <span>↗</span></button>'+['ox','fuel'].map(s=>`<button class="tree-item ${section===s?'active':''}" data-section="${s}"><span class="legend-dot ${s}"></span>${s==='ox'?'Oxidator':'Brennstoff'}<span>↗</span></button>`).join('')+project.nodes.filter(n=>!n.section).map(n=>`<button class="tree-item" data-select="${esc(n.id)}">${esc(n.label)}<span>·</span></button>`).join('');
 renderInspector();renderResults();renderGraph();
}
const fittingFields=[['diameterMm','Bezugsdurchmesser','mm',1,200,1],['k','Örtlicher Verlustbeiwert K','–',0,100,.1]];
const fields={turn:fittingFields,manifold:fittingFields,
 ...Object.fromEntries(Object.entries(COMPONENT_FIELDS).map(([type,items])=>[type,items.map(f=>[f.key,f.label,f.unit,f.min,f.max,f.step])])),
 source:[['pressureBar','Verfügbarer Druck','bar',2,200,1],['temperatureK','Temperatur','K',85,303,.1]],
 line:[['lengthM','Länge','m',0,20,.1],['diameterMm','Innendurchmesser','mm',1,200,1],['roughnessMm','Rauheit','mm',0,1,.001],['k','Örtlicher Verlust K','–',0,100,.1]],
 valve:[['k','Verlustbeiwert K','–',0,100,.1]],
 injector:[['fuelDropBar','Druckverlust Brennstoff','bar',0,50,.5],['oxDropBar','Druckverlust Oxidator','bar',0,50,.5]],
};
const designFields=[['thrustN','Zielschub (ideal)','N',100,100000,100],['pcBar','Kammerdruck','bar',10,80,1],['of','Mischungsverhältnis O/F','–',2,3.2,.05],['eps','Expansion Ae/At','–',4,40,1],['paBar','Umgebungsdruck','bar',0,1.2,.01],['lstarM','Charakteristische Länge L*','m',.2,3,.05],['contractionRatio','Kontraktion Ac/At','–',1.5,8,.1]];
function field([key,label,unit,min,max,step],value,scope='design'){const draft=invalidDrafts.get(draftKey(selectedId,scope,key));return `<label class="field"><span>${label}</span><span class="field-input"><input type="number" data-field="${key}" data-scope="${scope}" value="${esc(draft?draft.value:Number(value))}" ${draft?'aria-invalid="true"':''} min="${min}" max="${max}" step="${['channelCount','stations'].includes(key)?1:'any'}" inputmode="decimal" required><span class="field-unit">${unit}</span></span><small class="field-hint">${min}–${max} ${unit}</small></label>`;}
function contourSvg(g){
 if(!g?.contour?.length)return '';
 const pts=g.contour.filter(p=>Number.isFinite(p.x)&&Number.isFinite(p.r));if(pts.length<2)return '';
 const minX=Math.min(...pts.map(p=>p.x)),maxX=Math.max(...pts.map(p=>p.x)),maxR=Math.max(...pts.map(p=>p.r));
 const sx=x=>20+(x-minX)/Math.max(maxX-minX,.001)*280,sy=r=>90-r/Math.max(maxR,.001)*65;
 const d=pts.map((p,i)=>`${i?'L':'M'}${sx(p.x)},${sy(p.r)}`).join(' ')+' '+[...pts].reverse().map(p=>`L${sx(p.x)},${sy(-p.r)}`).join(' ')+' Z';
 return `<svg viewBox="0 0 320 180" role="img" aria-label="Vorläufige Brennkammer- und Düsenkontur"><defs><pattern id="contourGrid" width="20" height="20" patternUnits="userSpaceOnUse"><path d="M20 0H0V20" fill="none" stroke="currentColor" opacity=".08"/></pattern></defs><rect width="320" height="180" fill="url(#contourGrid)"/><path d="${d}" fill="rgba(238,181,100,.07)" stroke="#eeb564" stroke-width="1.8"/><path d="M10 90H310" stroke="currentColor" opacity=".25" stroke-dasharray="4 4"/><text x="20" y="171" fill="currentColor" font-size="9">${stale()?'VERALTET · ':''}2D · NÄHERUNGSKONTUR</text></svg>`;
}
function renderInspector(){
 const n=project.nodes.find(n=>n.id===selectedId);if(!n)selectedId='design';
 $('#selection-tag').textContent=n?n.type.toUpperCase():'DESIGN';
 if(!n){
  $('#inspector').innerHTML=`${project.nodes.some(n=>n.type==='line')?'<button class="button full-width" data-action="compact-feedlines">Leitungen in Pfeile übernehmen</button>':''}<div class="eyebrow">CYCLE DESIGN · LOX / RP-1</div><h1>Dein Triebwerk.</h1><p class="help-text">Ein Betriebspunkt. Ein gemeinsames System. Beginne mit den Entwurfszielen.</p><div class="form-section">${designFields.map(f=>field(f,project.design[f[0]])).join('')}</div><div class="notice">Ideale Zielauslegung. Versorgungsdruck wird rückwärts ermittelt; kein automatischer Off-design-Betriebspunkt.</div>${result?.ok?`<div class="geometry-preview">${contourSvg(result.geometry)}</div>`:''}<button class="button button-quiet full-width" data-action="model">Modell & Gültigkeitsbereich ↗</button>`;
  return;
 }
 let body=`<div class="eyebrow">${n.medium==='ox'?'OXIDATOR · LOX':n.medium==='fuel'?'BRENNSTOFF · RP-1':n.medium==='mechanical'?'MECHANISCHER ANTRIEB':'HEISSGAS · ANTRIEB / SCHUB'}</div><h2>${esc(TYPES[n.type])}</h2><label class="field"><span>Bezeichnung</span><input data-label value="${esc(n.label)}" maxlength="80"></label>`;
 if(['line','turn','manifold','valve','sensor','pump'].includes(n.type))body+=`<div class="field-grid"><label class="field"><span>Medium</span><select data-medium><option value="ox" ${n.medium==='ox'?'selected':''}>LOX</option><option value="fuel" ${n.medium==='fuel'?'selected':''}>RP-1</option></select></label><label class="field"><span>Section</span><select data-section-select><option value="">Systemebene</option><option value="ox" ${n.section==='ox'?'selected':''}>Oxidator</option><option value="fuel" ${n.section==='fuel'?'selected':''}>Brennstoff</option></select></label></div>`;
 if(n.type==='valve')body+=`<label class="toggle-field"><input type="checkbox" aria-label="Ventil geöffnet" data-open ${n.params.open?'checked':''}><span>Ventil geöffnet</span><span class="badge">${n.params.open?'OPEN':'CLOSED'}</span></label>`;
 if(n.type==='regen')body+=n.params.mode==='channels'?`<div class="notice"><strong>1D-Kanalmodell · ${n.params.flowDirection==='co'?'Gleichstrom':'Gegenstrom'}</strong><br>Kontur aus Brennkammer und Hauptdüse. Massenstrom und Eintrittszustand aus dem Brennstoffpfad. Wärmeaufnahme und Druckverlust werden berechnet.</div>`:`<div class="notice">Altmodell: vorgegebener Wärmestrom und Druckverlust bleiben für dieses Projekt erhalten.</div><button class="button full-width" data-action="upgrade-cooling">Auf Kühlkanäle umstellen</button>`;
 if(['turn','manifold'].includes(n.type))body+=`<p class="help-text">${n.type==='manifold'?'Ein-/Austrittsverteiler für einen Kühlmantel; ein aggregierter Fluidpfad, keine Netzverzweigung.':'Hydraulische Umlenkung im Fluidpfad; kein automatischer zweiter Kühlpass.'} Δp = K · ρ · v² / 2 am eingegebenen Bezugsdurchmesser.</p>`;
 if(n.type==='regen'&&n.params.mode==='channels')body+=`<button class="button full-width" data-section="cooling">Kühlstrecke & Richtung einstellen ↗</button>`;
 const componentFields=n.type==='regen'&&n.params.mode==='channels'?CHANNEL_FIELDS.map(f=>[f.key,f.label,f.unit,f.min,f.max,f.step]):(fields[n.type]||[]);
 body+=componentFields.map(f=>{const spec=[...f];if(n.type==='source'&&f[0]==='temperatureK'){spec[3]=n.medium==='ox'?85:288;spec[4]=n.medium==='ox'?95:303;}return field(spec,n.params[f[0]],'params');}).join('');
 if(n.type==='sensor')body+=`<label class="field"><span>Messgröße</span><select data-quantity><option value="pressure" ${n.params.quantity==='pressure'?'selected':''}>Druck</option><option value="temperature" ${n.params.quantity==='temperature'?'selected':''}>Temperatur (Annahme)</option><option value="massflow" ${n.params.quantity==='massflow'?'selected':''}>Massenstrom</option></select></label><p class="help-text">Ideale Messstelle ohne Druckverlust. Zum Einfügen eine Verbindung trennen und über die Messstelle neu verbinden.</p>`;
 if(n.type==='chamber'||n.type==='nozzle')body+=`<div class="form-section">${designFields.filter(f=>n.type==='chamber'?['thrustN','pcBar','of','lstarM','contractionRatio'].includes(f[0]):['eps','paBar'].includes(f[0])).map(f=>field(f,project.design[f[0]])).join('')}</div>${result?.ok?`<div class="geometry-preview">${contourSvg(result.geometry)}</div><div class="pressure-row"><span>Halsdurchmesser</span><strong>${num(result.geometry.throatRadiusM*2000,1)} mm</strong></div><div class="pressure-row"><span>Austrittsdurchmesser</span><strong>${num(result.geometry.exitRadiusM*2000,1)} mm</strong></div>`:'<p class="help-text">Nach der Berechnung erscheint hier die 2D-Kontur.</p>'}`;
 if(COMPONENT_NOTES[n.type]&&!(n.type==='regen'&&n.params.mode==='channels'))body+=`<div class="notice">${esc(COMPONENT_NOTES[n.type])}</div>`;
 if(['pump','turbine'].includes(n.type))body+=`<label class="field"><span>Antriebswelle</span><select data-shaft><option value="">Welle auswählen</option>${project.nodes.filter(x=>x.type==='shaft').map(x=>`<option value="${esc(x.id)}" ${n.params.shaftId===x.id?'selected':''}>${esc(x.label)}</option>`).join('')}</select></label>`;
 if(n.type==='regen'&&n.params.mode==='channels')body+=`<p class="help-text">Rechteckkanäle mit lokalem Teilungsanteil: Breite folgt dem Umfang. Kühlmittel: n-Dodecan als RP-1-Ersatzstoff. Gasrandbedingung aus CEA; keine Rückkopplung der Brennstoffenthalpie in die Verbrennungschemie.</p><button class="button full-width" data-action="cooling-details">Temperaturprofil & Kanalwerte ↗</button>`;
 if(['chamber','nozzle'].includes(n.type)){const cooling=project.nodes.find(x=>x.type==='regen'&&x.params.mode==='channels');if(cooling)body+=`<button class="button full-width" data-select="${esc(cooling.id)}">Gekoppelte Kühlkanäle öffnen ↗</button>`;}
 const station=result?.ok&&result.stations?.[n.id];
 if(station)body+=`<div class="form-section"><div class="section-label">${stale()?'LETZTER STAND · VERALTET':'BERECHNETER ZUSTAND'}</div><div class="pressure-row"><span>${n.medium==='gas'?'Modelldruck':'Erforderl. Eintrittsdruck'}</span><strong>${num(station.pressureBar)} bar</strong></div><div class="pressure-row"><span>Massenstrom</span><strong>${num(station.massFlowKgS,3)} kg/s</strong></div><div class="pressure-row"><span>Temperatur (Annahme)</span><strong>${num(station.temperatureK,1)} K</strong></div><div class="pressure-row"><span>Druckverlust</span><strong>${num(station.dropBar,3)} bar</strong></div></div>`;
 if(n.type==='source')body+=`<p class="help-text">Konstante Randbedingung, kein dynamisches Tankmodell. ${n.medium==='fuel'?'RP-1: konstante Screeningwerte für Dichte und Viskosität.':'Einphasiger LOX-Versorgungspfad mit konstanten Screeningwerten.'}</p>`;
 if(n.type==='line')body+='<p class="help-text">Die physische Länge bleibt beim Verschieben im Systemplan unverändert.</p>';
 if(n.type!=='shaft')body+=`<div class="form-section"><div class="section-label">ANSCHLÜSSE</div>${project.edges.filter(e=>e.from===n.id||e.to===n.id).map(e=>`<div class="connection-row"><span>${esc(project.nodes.find(x=>x.id===e.from)?.label)} → ${esc(project.nodes.find(x=>x.id===e.to)?.label)}</span><button class="icon-button" data-disconnect="${esc(e.id)}" aria-label="Verbindung trennen">×</button></div>`).join('')||'<p class="help-text">Noch nicht verbunden. Ausgangsport und anschließend Eingangsport anklicken.</p>'}</div>`;
 if(!['nozzle','exhaust','shaft'].includes(n.type)){const targets=project.nodes.filter(b=>b.id!==n.id&&!['source','gasSource','shaft'].includes(b.type)&&(b.medium===n.medium||(b.type==='injector'&&['fuel','ox'].includes(n.medium)))&&!project.edges.some(e=>e.from===n.id&&e.to===b.id));if(targets.length)body+=`<label class="field"><span>Ausgang verbinden mit</span><select id="connection-target">${targets.map(b=>`<option value="${esc(b.id)}">${esc(b.label)}</option>`).join('')}</select></label><button class="button full-width" data-action="connect-inspector">Verbindung hinzufügen</button>`;}
 if(['line','turn','manifold','valve','sensor','pump','regen'].includes(n.type)&&!project.edges.some(e=>e.from===n.id||e.to===n.id)){const edges=project.edges.filter(e=>{const a=project.nodes.find(x=>x.id===e.from),b=project.nodes.find(x=>x.id===e.to);return a?.medium===n.medium&&(b?.medium===n.medium||b?.type==='injector');});if(edges.length)body+=`<label class="field"><span>In Versorgungspfad einsetzen</span><select id="insert-edge">${edges.map(e=>`<option value="${esc(e.id)}">${esc(project.nodes.find(x=>x.id===e.from)?.label)} → ${esc(project.nodes.find(x=>x.id===e.to)?.label)}</option>`).join('')}</select></label><button class="button full-width" data-action="insert-component">In Leitung einsetzen</button>`;}
 if(n.section)body+=`<button class="button button-quiet full-width" data-section="${n.section}">Section öffnen ↗</button>`;
 $('#inspector').innerHTML=body;
}
function renderResults(){
 const outdated=stale();let status=running?'Berechnung läuft':!result?'Bereit für den ersten Lauf':outdated?'Entwurf geändert · neu berechnen':!result.ok?'Eingaben prüfen':(Object.values(result.feeds||{}).some(f=>f.marginBar<0)||(result.cycle?.shafts||[]).some(s=>!s.feasible))?'Versorgung / Antrieb prüfen':(result.cycle?.cooling||[]).some(c=>c.feasible===false)?'Wandtemperaturlimit überschritten':'Auslegung berechnet';
 const p=result?.ok?result.performance:null;
 $('#results').innerHTML=`<div class="run-status" role="status" aria-live="polite"><div class="eyebrow">ANALYSIS / 01</div><div><span class="status-dot ${outdated?'warning':result&&!result.ok?'error':''}"></span><strong>${status}</strong></div><span class="muted">${p?'CEA-Datenfeld · ideal · stationär':'Lokale Berechnung · kein Cloud-Upload'}</span></div>${[['Hauptschub',p?.thrustN/1000,'kN',2],['Haupt-Isp',p?.ispS,'s',1],['Massenstrom',p?.mdotKgS,'kg/s',3],['Kammertemperatur',p?.tcK,'K',0]].map(([label,v,u,d])=>`<div class="metric"><span>${label}</span><div><strong class="metric-value">${p?num(v,d):'—'}</strong><span class="metric-unit">${u}</span></div></div>`).join('')}<button class="button button-quiet result-open" id="result-details">${result?'Auswertung ↗':'So funktioniert’s ↗'}</button><div class="mobile-results-detail">${result?resultDetails():'<p>Wähle einen Entwurf und starte „Berechnen“.</p>'}</div>`;
 const runLabel=running?'Abbrechen':'Berechnen <span aria-hidden="true">↗</span>';if($('#run').innerHTML!==runLabel)$('#run').innerHTML=runLabel;
 $('#run').disabled=!thermo;
}
function resultDetails(){
 if(!result)return '';
 if(!result.ok)return `<h2>Der Entwurf benötigt eine Korrektur.</h2><ul class="issue-list">${result.errors.map(e=>`<li>${e.edgeId?`<button class="button button-quiet" data-error-edge="${esc(e.edgeId)}">Feedline zeigen ↗</button>`:e.nodeId?`<button class="button button-quiet" data-error-node="${esc(e.nodeId)}">Bauteil zeigen ↗</button>`:''}${esc(e.message)}</li>`).join('')}</ul>`;
 return `${stale()?'<div class="notice">Diese Ergebnisse gehören zum vorherigen Entwurfsstand. Bitte neu berechnen.</div>':''}<div class="eyebrow">VERSORGUNG AM AUSLEGUNGSPUNKT</div><h2>Passt dein Feed-System?</h2><p class="help-text">Erforderlicher Druck aus Kammerdruck und Verlusten. Überschuss ist Reserve bzw. notwendige Druckanpassung, kein automatisch erreichter Betriebspunkt.</p>${Object.entries(result.feeds).map(([key,f])=>`<div class="feed-result"><h3><i class="legend-dot ${key}"></i>${key==='ox'?'LOX · Oxidator':'RP-1 · Brennstoff'}</h3><div class="pressure-row"><span>Erforderlich</span><strong>${num(f.requiredBar)} bar</strong></div><div class="pressure-row"><span>Verfügbar</span><strong>${num(f.availableBar)} bar</strong></div><div class="pressure-track"><span style="width:${Math.max(0,Math.min(100,f.requiredBar/Math.max(f.availableBar,1)*100))}%"></span></div><div class="pressure-row ${f.marginBar<0?'danger':'success'}"><span>${f.marginBar<0?'Fehlender Druck':'Druckreserve'}</span><strong>${num(Math.abs(f.marginBar))} bar</strong></div></div>`).join('')}${cycleResults(result,esc,num,Object.fromEntries(project.nodes.map(n=>[n.id,n.label])),coolingViews)}<div class="geometry-preview">${contourSvg(result.geometry)}</div><details><summary>Stationen & Druckverluste</summary><div class="table-scroll"><table><thead><tr><th>Komponente</th><th>Erf. Eintritt / Modelldruck [bar]</th><th>Δp [bar]</th><th>ṁ [kg/s]</th></tr></thead><tbody>${Object.entries(result.stations||{}).map(([id,s])=>`<tr><td>${esc(project.nodes.find(n=>n.id===id)?.label||id)}</td><td>${num(s.pressureBar)}</td><td>${num(s.dropBar,3)}</td><td>${num(s.massFlowKgS,3)}</td></tr>`).join('')}</tbody></table></div></details><details open><summary>Modellhinweise</summary><ul class="issue-list">${(result.warnings||[]).map(w=>`<li>${esc(w)}</li>`).join('')}</ul><p class="help-text">${esc(typeof result.meta?.source==='string'?result.meta.source:JSON.stringify(result.meta?.source||{}))}<br>${esc(result.meta?.domain||'')}</p></details><div class="dialog-actions"><button class="button" data-action="csv">CSV exportieren</button><button class="button" data-action="json-results">Ergebnis-JSON</button></div>`;
}
function showDialog(title,body){const d=$('#dialog');d.dataset.thermal=String(title==='Thermische Auswertung');d.dataset.results=String(['Auswertung','Thermische Auswertung','Berechnung prüfen'].includes(title));d.innerHTML=`<div class="dialog-header"><span class="eyebrow">ASTROFORGE 2.3 LITE</span><button class="icon-button" data-close aria-label="Schließen">×</button></div><div class="dialog-body"><h2>${esc(title)}</h2>${body}</div>`;if(!d.open)d.showModal();}
function showHelp(){showDialog('Ein Triebwerk. Eine Arbeitsfläche.',`<div class="notice"><strong>Stand 2.3.1 · Triebwerksrahmen im Systemplan</strong><br>Neu: Die Triebwerks-Section rahmt Injektorkopf, Brennkammer und Hauptdüse im Systemplan ein. Kühlstrecke und Strömungsrichtung sind über den Kühlmantel erreichbar. Verbindungspfeile sind parametrierbare Feedlines mit stationären Zuständen. Über „Vorlage → Pumpen & Kühlung“ ausprobieren. Bestehende Projekte bleiben unverändert; alte Kühlblöcke lassen sich im Inspector umstellen.</div><p>AstroForge Lite verbindet einen bearbeitbaren Systemplan mit einem stationären Triebwerksvorentwurf.</p><ol class="help-steps"><li><strong>Entwurf definieren.</strong> Zielwerte im Inspector einstellen.</li><li><strong>System aufbauen.</strong> Bauteile ziehen oder antippen. Ausgangsport, dann Eingangsport anklicken. Verbindungen im Inspector trennen.</li><li><strong>Details öffnen.</strong> Oxidator- oder Brennstoff-Section öffnen. Bauteil auswählen und Parameter bearbeiten.</li><li><strong>Berechnen & prüfen.</strong> Leistung und erforderliche Versorgungsdrücke gemeinsam bewerten.</li></ol><div class="notice">Lite unterstützt zwei LOX/RP-1-Versorgungspfade mit Pumpen, Wellenbilanz und einem kanalaufgelösten regenerativen Kühlmodell. Ein separater Treibgaszweig versorgt Turbine und Abgasdüse. Das Kanalmodell koppelt CEA-Gasrandbedingungen, Wandwärmeleitung und Kühlmittelströmung. n-Dodecan dient als RP-1-Ersatzstoff. Kein Verbrennungsenthalpie-, Gasgenerator-, Festigkeits- oder Off-design-Nachweis.</div><h3>Berechnung auf deinem Gerät</h3><p>Thermochemie aus einem vorab mit RocketCEA erzeugten Datenfeld, innerhalb seiner Grenzen interpoliert. Druckverluste und Geometrie werden lokal neu berechnet. Das ist kein laufender CEA-Solver im Browser.</p><p class="help-text">Geometrie ist eine Vorentwurfsdarstellung. Stoffannahmen und Datenbereich stehen bei den Ergebnissen. Lokales Autosave bleibt auf diesem Gerät; für einen Gerätewechsel die Projektdatei speichern und öffnen.</p><h3>Windows & Android</h3><p>Im Browser nutzbar. Über das Browsermenü zum Startbildschirm hinzufügen, sofern die Installation angeboten wird. Die lokale Windows-Version kann nach dem ersten vollständigen Laden offline arbeiten. Beim privaten Hosting kann der Zugriff weiterhin eine Anmeldung bzw. Internetverbindung benötigen.</p><button class="button button-primary" data-close>Mit dem Entwurf beginnen</button>`);}
function download(name,text,type='application/json'){const u=URL.createObjectURL(new Blob([text],{type}));const a=document.createElement('a');a.href=u;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),1500);}
function save(){if(invalidDrafts.size){showInvalidDraft();return;}download(project.name.replace(/[^a-zA-Z0-9_-]+/g,'-')+'.astroforge.json',JSON.stringify(project,null,2));toast('Projektdatei gespeichert.');}
function exportResult(csv=false){if(!result)return;if(stale()){toast('Entwurf wurde geändert. Vor dem Export neu berechnen.');return;}if(csv){const q=v=>'"'+String(v??'').replaceAll('"','""')+'"';const rows=[['component','required_entry_or_model_pressure_bar','mass_flow_kg_s','pressure_drop_bar','temperature_K_assumed','model','source','computed_at','status','warnings'],...Object.entries(result.stations||{}).map(([id,s])=>[id,s.pressureBar,s.massFlowKgS,s.dropBar,s.temperatureK,result.meta?.model,result.meta?.source,result.computedAt,Object.values(result.feeds||{}).some(f=>f.marginBar<0)?'underpressure':(result.cycle?.shafts||[]).some(s=>!s.feasible)?'insufficient_drive':(result.cycle?.cooling||[]).some(c=>c.feasible===false)?'wall_limit_exceeded':'calculated',result.warnings.join(' | ')])];download('astroforge-stations.csv',rows.map(r=>r.map(q).join(',')).join('\r\n'),'text/csv;charset=utf-8');}else download('astroforge-results.json',JSON.stringify({project,computedAt:result.computedAt,result},null,2));}
function connect(from,to){
 const a=project.nodes.find(n=>n.id===from),b=project.nodes.find(n=>n.id===to);if(!a||!b||from===to)return;
 if(project.edges.some(e=>e.from===from&&e.to===to)){toast('Diese Verbindung besteht bereits.');return;}
 if(['nozzle','exhaust','shaft'].includes(a.type)||['source','gasSource','shaft'].includes(b.type)){toast('Diese Anschlussrichtung ist nicht möglich.');return;}
 if(a.medium!==b.medium&&!(b.type==='injector'&&['fuel','ox'].includes(a.medium))){toast('Medien passen nicht zusammen.');return;}
 const origin=project.nodes.find(n=>n.id===from);const pipe=['fuel','ox'].includes(origin?.medium)?{lengthM:0,diameterMm:project.edges.find(e=>e.to===from)?.pipe?.diameterMm??(origin.medium==='ox'?22:18),roughnessMm:.01,k:0}:undefined;mutate(p=>p.edges.push({id:uid(),from,to,...(pipe?{pipe}:{})}));toast('Verbindung hergestellt.');
}
function addNode(type,medium=section==='ox'?'ox':'fuel'){
 if(['injector','chamber','nozzle'].includes(type)&&project.nodes.some(n=>n.type===type)){toast('Lite unterstützt genau eine '+TYPES[type]+'.');return;}
 const params=clone(DEFAULT_PARAMS[type]||{});
 if(type==='regen')medium='fuel';
 if(['injector','chamber','nozzle','gasSource','turbine','exhaust'].includes(type))medium='gas';
 if(type==='shaft')medium='mechanical';
 if(type==='source')params.temperatureK=medium==='ox'?90:293.15;
 if(['pump','turbine'].includes(type))params.shaftId=project.nodes.find(n=>n.type==='shaft')?.id||'';
 const id=uid();mutate(p=>p.nodes.push({id,type,label:TYPES[type]+' '+(p.nodes.filter(n=>n.type===type).length+1),medium,section:['line','turn','manifold','valve','sensor','pump','regen'].includes(type)?medium:null,x:340+(p.nodes.length%3)*190,y:600,params}));selectedId=id;render();setPanel('inspector');toast('Bauteil hinzugefügt. Im Inspector einsetzen oder Anschlüsse verbinden.');
}
function deleteSelected(){const n=project.nodes.find(n=>n.id===selectedId);if(!n){toast('Zuerst eine Komponente auswählen.');return;}for(const [key,draft] of invalidDrafts)if(draft.id===n.id)invalidDrafts.delete(key);mutate(p=>{p.nodes=p.nodes.filter(x=>x.id!==n.id);p.edges=p.edges.filter(e=>e.from!==n.id&&e.to!==n.id);});selectedId='design';render();toast('Komponente entfernt · mit ↶ rückgängig machen.');}
function stopJob(){if(worker){worker.terminate();worker=null;}running=false;jobId++;}
function showInvalidDraft(){if($('#dialog').open)$('#dialog').close();const draft=invalidDrafts.values().next().value;if(!draft)return;if(draft.scope==='edge'){graph.selectedEdge=draft.id;section=null;setPanel('canvas');render();graph.edgePanel.querySelector('input[aria-invalid]')?.focus();toast('Ungültigen Feedline-Wert korrigieren oder rückgängig machen.');return;}selectedId=draft.scope==='design'?'design':draft.id;renderInspector();setPanel('inspector');const field=$('#inspector input[aria-invalid="true"]');field?.focus();toast('Ungültige Eingabe beibehalten. Bitte korrigieren oder mit Rückgängig verwerfen.');}
function run(){
 if(running){stopJob();renderResults();toast('Berechnung abgebrochen.');return;}
 if(!thermo){toast('Thermochemiedaten werden noch geladen.');return;}
 if(invalidDrafts.size){showInvalidDraft();return;}
 const invalid=[...document.querySelectorAll('#inspector input[data-field]')].find(el=>el.value.trim()===''||!el.checkValidity());if(invalid){invalid.setAttribute('aria-invalid','true');invalid.focus();toast('Bitte die ungültige Eingabe korrigieren. Es wurde nicht mit einem alten Wert gerechnet.');return;}
 const snapshot=clone(project),key=fingerprint(snapshot),id=++jobId;running=true;renderResults();
 worker=new Worker('./src/worker.js',{type:'module'});
 worker.onmessage=({data})=>{if(data.id!==jobId)return;result=data.result;result.computedAt=new Date().toISOString();resultKey=key;worker.terminate();worker=null;running=false;render();if($('#dialog').open&&$('#dialog').dataset.results==='true')refreshCoolingViews();if(!result.ok){toast('Bitte markierte Eingaben oder Verbindungen prüfen.');showDialog('Berechnung prüfen',resultDetails());}else toast(stale()?'Ergebnis gehört zum vorherigen Entwurf.':'Auslegung berechnet. Versorgungsbilanz verfügbar.');};
 worker.onerror=()=>{stopJob();toast('Berechnung konnte nicht gestartet werden. Bitte neu laden.');renderResults();};
 worker.postMessage({id,project:snapshot,thermo,coolingData});
}
function undo(){if(invalidDrafts.size){invalidDrafts.clear();render();toast('Ungültige Eingabe verworfen.');return;}project=history.undo();persist();render();}function redo(){if(invalidDrafts.size){showInvalidDraft();return;}project=history.redo();persist();render();}
$('#palette').innerHTML=Object.entries(TYPES).filter(([type])=>type!=='line').map(([type,label])=>`<button class="palette-item" draggable="true" data-add="${type}" title="${label} hinzufügen"><span class="component-icon">${({source:'▤',turn:'↪',manifold:'⊢',line:'━',valve:'⋈',sensor:'◎',pump:'◉',regen:'≋',shaft:'⚙',gasSource:'▤',turbine:'✺',exhaust:'⋙',injector:'▥',chamber:'▰',nozzle:'⋙'})[type]}</span><span>${label}</span><span class="muted">+</span></button>`).join('');
$('#palette').addEventListener('dragstart',e=>{const b=e.target.closest('[data-add]');if(b)e.dataTransfer.setData('text/plain',b.dataset.add);});
$('#canvas').addEventListener('dragover',e=>e.preventDefault());$('#canvas').addEventListener('drop',e=>{e.preventDefault();const type=e.dataTransfer.getData('text/plain');if(Object.hasOwn(TYPES,type))addNode(type);});
document.addEventListener('click',e=>{
 const t=e.target.closest('button');if(!t)return;
 if(t.dataset.panel)setPanel(t.dataset.panel);
 if(t.dataset.section){section=t.dataset.section==='root'?null:t.dataset.section;setPanel('canvas');render();graph.fit();}
 if(t.dataset.select){selectedId=t.dataset.select;render();if(innerWidth<900)setPanel('inspector');}
 if(t.dataset.add)addNode(t.dataset.add);
 if(t.hasAttribute('data-close'))$('#dialog').close();
 if(t.dataset.disconnect)mutate(p=>p.edges=p.edges.filter(x=>x.id!==t.dataset.disconnect));
 if(t.dataset.errorEdge){graph.selectedEdge=t.dataset.errorEdge;$('#dialog').close();section=null;setPanel('canvas');render();graph.fit();}
 if(t.dataset.errorNode){selectedId=t.dataset.errorNode;$('#dialog').close();render();setPanel('inspector');}
 if(t.dataset.action==='insert-component'){const edgeId=$('#insert-edge')?.value;mutate(p=>{const e=p.edges.find(x=>x.id===edgeId),n=p.nodes.find(x=>x.id===selectedId);if(!e||!n)return;const a=p.nodes.find(x=>x.id===e.from),b=p.nodes.find(x=>x.id===e.to);n.x=(a.x+b.x)/2;n.y=(a.y+b.y)/2+140;p.edges=p.edges.filter(x=>x.id!==edgeId);p.edges.push({...e,id:uid(),from:e.from,to:n.id},{id:uid(),from:n.id,to:e.to});});toast('Komponente in den Versorgungspfad eingesetzt.');}
 if(t.dataset.action==='compact-feedlines'){mutate(p=>Object.assign(p,compactFeedlines(p)));toast('Leitungswerte in Verbindungspfeile übernommen. Rückgängig ist möglich.');}
 if(t.dataset.action==='attach-cooling'){if(project.nodes.some(n=>n.type==='regen')){toast('Ein Kühlbauteil ist bereits vorhanden. Im Inspector auf Kanalmodell umstellen.');return;}const inj=project.nodes.find(n=>n.type==='injector'),edge=project.edges.find(e=>e.to===inj?.id&&project.nodes.find(n=>n.id===e.from)?.medium==='fuel');if(!edge){toast('Zuerst den Brennstoffpfad mit dem Injektor verbinden.');return;}const id=uid();mutate(p=>{p.nodes.push({id,type:'regen',label:'Kühlmantel',medium:'fuel',section:'fuel',x:inj.x,y:inj.y+180,params:{...CHANNEL_DEFAULTS}});p.edges.find(e=>e.id===edge.id).to=id;p.edges.push({id:uid(),from:id,to:inj.id});});selectedId=id;render();}
 if(t.dataset.action==='upgrade-cooling'){if(invalidDrafts.size){showInvalidDraft();return;}mutate(p=>{const n=p.nodes.find(x=>x.id===selectedId);if(n?.type==='regen')n.params=clone(CHANNEL_DEFAULTS);});toast('Kanalmodell aktiviert. Die Geometrie stammt aus dem Triebwerksentwurf.');}
 if(t.dataset.action==='cooling-details'){if(result?.ok)showDialog('Thermische Auswertung',thermalDetails());else toast('Bitte zuerst den Entwurf berechnen.');}
 if(t.dataset.coolingView){const id=t.dataset.coolingNode;coolingViews[id]={...coolingViews[id],view:t.dataset.coolingView};refreshCoolingViews();}
 if(t.dataset.coolingIndex!==undefined){const id=t.dataset.coolingNode;coolingViews[id]={...coolingViews[id],station:Number(t.dataset.coolingIndex)};refreshCoolingViews();}
 if(t.dataset.action==='cooling-csv')exportCooling(t.dataset.coolingNode);
 if(t.dataset.action==='model')showHelp();
 if(t.dataset.action==='connect-inspector')connect(selectedId,$('#connection-target').value);
 if(t.dataset.action==='csv')exportResult(true);if(t.dataset.action==='json-results')exportResult();
 if(t.id==='result-details'){if(result)showDialog('Auswertung',resultDetails());else showHelp();}
});
function thermalDetails(){
 if(!result?.ok)return resultDetails();
 const content=coolingResults(result,esc,num,Object.fromEntries(project.nodes.map(n=>[n.id,n.label])),coolingViews);
 return `${stale()?'<div class="notice">Veralteter Entwurfsstand. Vor Bewertung und Export neu berechnen.</div>':''}${content||'<p>Für diesen berechneten Stand liegt noch kein Kanalprofil vor. Bitte neu berechnen.</p>'}<p class="help-text">Stoffmodell: CoolProp n-Dodecan als RP-1-Ersatzstoff. CEA-Gasrandbedingungen mit frozen-Transportdaten für Bartz; keine Rückkopplung in die Verbrennungschemie.</p>`;
}
function refreshCoolingViews(){
 const dialog=$('#dialog'),results=$('#results'),dialogOpen=dialog.open&&dialog.dataset.results==='true',dialogScroll=dialog.scrollTop,resultsScroll=results.scrollTop;
 const thermalOnly=dialog.dataset.thermal==='true';
 const containers=dialogOpen?[results,dialog]:[results];
 const openDetails=containers.map(container=>new Set([...container.querySelectorAll('details[open]')].map(d=>d.querySelector('summary')?.textContent)));
 const active=document.activeElement,keys=['coolingView','coolingNode','coolingStation','coolingIndex','action'];
 const focus=active&&containers.some(c=>c.contains(active))?{tag:active.tagName,data:Object.fromEntries(keys.filter(k=>active.dataset[k]!==undefined).map(k=>[k,active.dataset[k]]))}:null;
 renderResults();if(dialogOpen)showDialog(thermalOnly?'Thermische Auswertung':'Auswertung',thermalOnly?thermalDetails():resultDetails());
 containers.forEach((container,i)=>container.querySelectorAll('details').forEach(d=>d.open=openDetails[i].has(d.querySelector('summary')?.textContent)));
 if(focus&&Object.keys(focus.data).length){const container=dialogOpen?dialog:results;[...container.querySelectorAll('button,select')].find(el=>el.tagName===focus.tag&&Object.entries(focus.data).every(([k,v])=>el.dataset[k]===v))?.focus({preventScroll:true});}
 if(dialogOpen)dialog.scrollTop=dialogScroll;results.scrollTop=resultsScroll;
}
function exportCooling(id){
 if(stale()){toast('Vor dem Export neu berechnen.');return;}
 const cooling=result?.cycle?.cooling?.find(c=>c.nodeId===id&&c.mode==='channels');if(!cooling?.stations?.length)return;
 const keys=Object.keys(cooling.stations[0]);const quote=v=>'"'+String(v??'').replaceAll('"','""')+'"';
 const rows=[[...keys,'computed_at','coolant_model','gas_boundary','pressure_basis','wall_limit_status','energy_residual_W','fuel_pressure_margin_bar'],...cooling.stations.map(row=>[...keys.map(k=>row[k]),result.computedAt,'CoolProp n-dodecane surrogate','CEA frozen chamber transport / Bartz','static coolant pressure at required feed operating point',cooling.feasible?'within_user_limit':'exceeds_user_limit',cooling.energyResidualW,result.feeds?.fuel?.marginBar])];
 download('astroforge-cooling-'+id+'.csv',rows.map(row=>row.map(quote).join(',')).join('\r\n'),'text/csv;charset=utf-8');
}
document.addEventListener('change',e=>{const id=e.target.dataset.coolingStation;if(id){coolingViews[id]={...coolingViews[id],station:Number(e.target.value)};refreshCoolingViews();}});
$('#inspector').addEventListener('input',e=>{
 const t=e.target;if(t.hasAttribute('data-label')){if(t.value.trim())mutate(p=>p.nodes.find(n=>n.id===selectedId).label=t.value.trim(),false);return;}if(!t.dataset.field)return;
 const token=draftKey(selectedId,t.dataset.scope,t.dataset.field);
 if(!Number.isFinite(Number(t.value))||t.value.trim()===''||!t.checkValidity()){invalidDrafts.set(token,{id:selectedId,scope:t.dataset.scope,value:t.value});t.setAttribute('aria-invalid','true');renderResults();renderGraph();updateHistory();return;}
 invalidDrafts.delete(token);t.removeAttribute('aria-invalid');const value=Number(t.value),key=t.dataset.field;
 mutate(p=>{if(t.dataset.scope==='design')p.design[key]=value;else {const node=p.nodes.find(n=>n.id===selectedId);if(node)node.params[key]=value;}},false);
 renderResults();updateHistory();
});
$('#inspector').addEventListener('change',e=>{
 const t=e.target,n=project.nodes.find(n=>n.id===selectedId);
 if(t.dataset.field){const v=t.value.trim()===''?NaN:Number(t.value);if(!Number.isFinite(v)||!t.checkValidity()){t.setAttribute('aria-invalid','true');toast('Bitte einen Wert innerhalb des angegebenen Bereichs eingeben.');return;}mutate(p=>{if(t.dataset.scope==='design')p.design[t.dataset.field]=v;else p.nodes.find(x=>x.id===selectedId).params[t.dataset.field]=v;});}
 else if(t.hasAttribute('data-label')&&n)mutate(p=>p.nodes.find(x=>x.id===n.id).label=t.value.trim()||TYPES[n.type]);
 else if(t.hasAttribute('data-medium')&&n)mutate(p=>{const node=p.nodes.find(x=>x.id===n.id);node.medium=t.value;if(node.section)node.section=t.value;});
 else if(t.hasAttribute('data-section-select')&&n)mutate(p=>p.nodes.find(x=>x.id===n.id).section=t.value||null);
 else if(t.hasAttribute('data-shaft')&&n)mutate(p=>p.nodes.find(x=>x.id===n.id).params.shaftId=t.value);
 else if(t.hasAttribute('data-open')&&n)mutate(p=>p.nodes.find(x=>x.id===n.id).params.open=t.checked);
 else if(t.hasAttribute('data-quantity')&&n)mutate(p=>p.nodes.find(x=>x.id===n.id).params.quantity=t.value);
});
$('#run').onclick=run;$('#help').onclick=showHelp;$('#save-project').onclick=save;$('#open-project').onclick=()=>$('#file-input').click();$('#undo').onclick=undo;$('#redo').onclick=redo;$('#fit').onclick=()=>graph.fit();$('#delete-node').onclick=deleteSelected;
$('#design-select').onclick=()=>{selectedId='design';render();setPanel('inspector');};
$('#project-name').onclick=()=>{showDialog('Projekt benennen',`<form id="rename-form"><label class="field"><span>Projektname</span><input name="name" maxlength="120" value="${esc(project.name)}" required></label><button class="button button-primary" type="submit">Übernehmen</button></form>`);$('#rename-form').onsubmit=e=>{e.preventDefault();const name=new FormData(e.target).get('name').trim();if(name)mutate(p=>p.name=name);$('#dialog').close();};};
$('#new-project').onclick=()=>{showDialog('Wähle deinen Cycle',`<p>Die Vorlage ersetzt den aktuellen Arbeitsstand. Speichere deinen Entwurf vorher als Datei.</p><div class="template-grid">${TEMPLATES.map((t,i)=>`<button class="template-card" data-template="${t.id}"><div class="eyebrow">${t.tag}</div><h3>${t.title}</h3><p>${t.description}</p><span class="button button-quiet">Vorlage laden ↗</span></button>`).join('')}</div><div class="notice">Turbinenantrieb: separat vorgegebener Treibgasstrom, kein geschlossener Gasgeneratorzyklus. Alle Vorlagen starten mit 10 kN Hauptschub.</div><div class="dialog-actions"><button class="button" id="save-before-new">Aktuelles Projekt speichern</button></div>`);$('#save-before-new').onclick=save;$('#dialog').querySelectorAll('[data-template]').forEach(b=>b.onclick=()=>{replaceProject(compactFeedlines(createTemplate(b.dataset.template)));$('#dialog').close();run();});};
$('#file-input').onchange=async e=>{const f=e.target.files[0];if(!f)return;try{if(f.size>2_000_000)throw Error('Projektdatei zu groß.');const next=parseProject(await f.text());showDialog('Projekt öffnen',`<p>„${esc(next.name)}“ ersetzt den aktuellen Arbeitsstand. Speichere diesen bei Bedarf zuerst.</p><div class="dialog-actions"><button class="button" id="save-before-open">Aktuelles Projekt speichern</button><button class="button button-primary" id="confirm-open">Projekt öffnen</button></div>`);$('#save-before-open').onclick=save;$('#confirm-open').onclick=()=>{replaceProject(next);$('#dialog').close();toast('Projekt geöffnet. Bitte neu berechnen.');};}catch(err){toast(err.message);}e.target.value='';};
document.addEventListener('keydown',e=>{const input=/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName);if($('#dialog').open)return;if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'){e.preventDefault();save();}if(input)return;if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();e.shiftKey?redo():undo();}if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='y'){e.preventDefault();redo();}if(e.key==='Delete')deleteSelected();});
$('#dialog').addEventListener('click',e=>{if(e.target===$('#dialog')){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)e.target.close();}});
render();
if(storageWarning)toast('Gespeichertes Projekt nicht lesbar. Vorlage geladen.');
try{[thermo,coolingData]=await Promise.all([loadThermo(),loadCoolingData()]);renderResults();run();}catch(error){toast('Rechen- oder Stoffdaten konnten nicht geladen werden.');showDialog('Daten nicht verfügbar',`<p>${esc(error.message)}</p><p>Bitte Verbindung prüfen und neu laden.</p>`);}
if('serviceWorker' in navigator)navigator.serviceWorker.register('./sw.js').catch(()=>{});

$('#engine-section').addEventListener('input',e=>{
 const key=e.target.dataset.coolingRange;if(!key)return;const id=e.target.closest('[data-regen]').dataset.regen;
 mutate(p=>{p.nodes.find(n=>n.id===id).params[key]=Number(e.target.value);},false);
});
$('#engine-section').addEventListener('change',e=>{
 if(e.target.hasAttribute('data-cooling-direction')){const id=e.target.closest('[data-regen]').dataset.regen;mutate(p=>p.nodes.find(n=>n.id===id).params.flowDirection=e.target.value,false);}
 // Rebuild bounds after a drag, without interrupting the native slider while moving.
 e.target.blur();render();
});

function feedlinePanel(edge){
 const from=project.nodes.find(n=>n.id===edge.from),to=project.nodes.find(n=>n.id===edge.to),liquid=['ox','fuel'].includes(from?.medium);
 const pipe=edge.pipe||{lengthM:0,diameterMm:from?.medium==='ox'?22:18,roughnessMm:.01,k:0};
 const station=result?.ok?result.edgeStates?.[edge.id]:null;
 const row=(label,value)=>`<div class="pressure-row"><span>${label}</span><strong>${value}</strong></div>`;
 const status=!result?'Noch nicht berechnet':stale()?'VERALTET · neu berechnen':result.ok?'STATIONÄR · ZIELBETRIEBSPUNKT':'Berechnung ungültig';
 return `<button class="icon-button" style="float:right" data-close-edge aria-label="Feedline-Panel schließen">×</button><div class="eyebrow edge-status">${status}</div><h3>${esc(from?.label)} → ${esc(to?.label)}</h3>${row('Medium',liquid?(from.medium==='ox'?'LOX':'RP-1 / n-Dodecan*'):'Heißgas')}${row('Temperatur',station?num(station.temperatureK,1)+' K':'—')}${row(liquid?'Erf. Gesamtdruck Eintritt':'Modelldruck',station?num(station.pressureBar,2)+' bar':'—')}${row('Druckverlust',station?num(station.dropBar,3)+' bar':'—')}${liquid?row('Erf. Gesamtdruck Austritt',station?num(station.outletPressureBar,2)+' bar':'—'):''}${row('Massenstrom',station?num(station.massFlowKgS,3)+' kg/s':'—')}${row('O/F',liquid?'Reiner Stoff':from?.type==='injector'||from?.type==='chamber'?num(project.design.of,2):'Nicht vorgegeben')}
 ${liquid?`<div class="edge-controls">${[['lengthM','Länge','m',0,100],['diameterMm','Durchmesser','mm',1,200],['roughnessMm','Rauheit','mm',0,1],['k','Verlustbeiwert K','–',0,10000]].map(([key,label,unit,min,max])=>`<label class="field"><span>${label} [${unit}]</span><input type="number" data-edge-param="${key}" ${invalidDrafts.has("edge:"+edge.id+":"+key)?'aria-invalid="true"':''} value="${esc(invalidDrafts.get("edge:"+edge.id+":"+key)?.value??pipe[key])}" min="${min}" max="${max}" step="any" required></label>`).join('')}</div><p class="help-text">Physische Länge unabhängig vom Pfeilverlauf. *Mit Kanalmodell temperaturabhängige Ersatzstoffdaten, sonst konstante RP-1-Werte. Angezeigt ist das erforderliche Druckbudget.</p>`:'<p class="help-text">Ideale Gasverbindung ohne eigene Leitungsverluste. Treibgaszustand vorgegeben; kein berechneter Gasgenerator und keine berechnete Gemischzusammensetzung.</p>'}`;
}
$('#canvas').addEventListener('click',e=>{if(e.target.closest('[data-close-edge]')){graph.selectedEdge=null;renderGraph();}});
$('#canvas').addEventListener('input',e=>{
 const key=e.target.dataset.edgeParam;if(!key)return;
 const id=e.target.closest('[data-edge-id]').dataset.edgeId,token='edge:'+id+':'+key;
 if(!e.target.checkValidity()||e.target.value.trim()===''){invalidDrafts.set(token,{scope:'edge',id,value:e.target.value});e.target.setAttribute('aria-invalid','true');renderResults();updateHistory();return;}
 invalidDrafts.delete(token);e.target.removeAttribute('aria-invalid');const value=Number(e.target.value);
 mutate(p=>{const edge=p.edges.find(v=>v.id===id),from=p.nodes.find(n=>n.id===edge.from);edge.pipe||={lengthM:0,diameterMm:from.medium==='ox'?22:18,roughnessMm:.01,k:0};edge.pipe[key]=value;},false);
 renderResults();
});

$('#canvas').addEventListener('change',e=>{if(e.target.dataset.edgeParam){e.target.blur();renderGraph();}});
