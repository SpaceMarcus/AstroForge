import {CHANNEL_DEFAULTS} from './cooling-config.js';
export const TYPES = {source:'Versorgung',coolantSource:'Kühlmittelversorgung',branch:'Abzweig',restriction:'Verengung',consumer:'Verbraucher / Preburner',line:'Leitung',turn:'Umlenkung',manifold:'Manifold',valve:'Ventil',sensor:'Messstelle',pump:'Pumpe',regen:'Regenerativkühlung',shaft:'Welle / Antrieb',gasSource:'Treibgasquelle',turbine:'Turbine',exhaust:'Abgasdüse',injector:'Injektor',chamber:'Brennkammer',nozzle:'Glockendüse'};
export const DEFAULT_PARAMS = {
 coolantSource:{pressureBar:60,temperatureK:293.15},branch:{diameterMm:18,k:0},restriction:{upstreamDiameterMm:18,diameterMm:10,k:1},consumer:{massFlowKgS:.2,pressureBar:25,purpose:'preburner'},
 turn:{diameterMm:18,k:1.5},manifold:{diameterMm:18,k:1,axialPosition:.5},
 source:{pressureBar:55,temperatureK:293.15},line:{lengthM:1,diameterMm:20,roughnessMm:.01,k:.5},valve:{k:2,open:true},sensor:{quantity:'pressure'},injector:{fuelDropBar:6,oxDropBar:6},
 pump:{riseBar:30,efficiency:.7,shaftId:''},regen:{...CHANNEL_DEFAULTS},shaft:{efficiency:.96,rpm:30000,motorKW:30},
 gasSource:{pressureBar:30,temperatureK:900,massFlowKgS:.15,cpJkgK:2200,gamma:1.25},turbine:{outletBar:2,efficiency:.7,shaftId:''},exhaust:{exitBar:1.01325,efficiency:.95},chamber:{},nozzle:{}
};
export const TEMPLATES = [
 {id:'cooling-network',name:'AF–04 / Cooling network',tag:'04 · BRANCHES',title:'Kühlung & Abzweige',description:'Eigene Cooling-Section, Kühlmantel und Abzweig zum Injektor und einem Preburner-Verbraucher.'},
 {id:'cooling-external',name:'AF–05 / Separate cooling supply',tag:'05 · COOLING SUPPLY',title:'Separate Kühlversorgung',description:'Unabhängige RP-1-Kühlversorgung mit eigenem Austrittsverbraucher.'},
 {id:'pressure',name:'AF–01 / Pressure-fed',tag:'01 · BASELINE',title:'Druckgefördert',description:'Zwei Versorgungspfade. Der klare Einstieg in deinen Triebwerksentwurf.'},
 {id:'electric',name:'AF–02 / Electric + Regen',tag:'02 · ELECTRIC',title:'Pumpen & Kühlung',description:'Zwei Pumpen, gemeinsamer elektrischer Antrieb und geometrisch definierte Kühlkanäle.'},
 {id:'turbine',name:'AF–03 / Turbine drive',tag:'03 · TURBINE',title:'Turbine & Abgasdüse',description:'Turbinenantrieb, Wellenbilanz und zweite Düse mit vorgegebenem Treibgasstrom.'}
];
export const clone = value => structuredClone(value);
export function createProject(name='AF–01 / Pressure-fed') {
  const node=(id,type,label,medium,section,x,y,params={})=>({id,type,label,medium,section,x,y,params});
  const nodes=[
    node('ox-source','source','LOX Versorgung','ox',null,40,90,{pressureBar:55,temperatureK:90}),
    node('ox-line','line','OX · Feed line','ox','ox',260,90,{lengthM:1.2,diameterMm:22,roughnessMm:.01,k:.5}),
    node('ox-valve','valve','OX · Main valve','ox','ox',480,90,{k:2,open:true}),
    node('fuel-source','source','RP-1 Versorgung','fuel',null,40,350,{pressureBar:55,temperatureK:293.15}),
    node('fuel-line','line','FU · Feed line','fuel','fuel',260,350,{lengthM:1.2,diameterMm:18,roughnessMm:.01,k:.5}),
    node('fuel-valve','valve','FU · Main valve','fuel','fuel',480,350,{k:2,open:true}),
    node('injector','injector','Injektorkopf','gas',null,720,220,{fuelDropBar:6,oxDropBar:6}),
    node('chamber','chamber','Brennkammer','gas',null,940,220),
    node('nozzle','nozzle','Bell nozzle','gas',null,1160,220),
  ];
  const pairs=[['ox-source','ox-line'],['ox-line','ox-valve'],['ox-valve','injector'],['fuel-source','fuel-line'],['fuel-line','fuel-valve'],['fuel-valve','injector'],['injector','chamber'],['chamber','nozzle']];
  return {format:'astroforge-lite',version:1,name,design:{thrustN:10000,pcBar:30,of:2.6,eps:12,paBar:1.01325,lstarM:1.1,contractionRatio:3},nodes,edges:pairs.map(([from,to],i)=>({id:'e'+i,from,to})),updatedAt:new Date().toISOString()};
}
export function fingerprint(project) {
  return JSON.stringify({design:project.design,nodes:project.nodes.map(({id,type,medium,section,params})=>({id,type,medium,section,params})).sort((a,b)=>a.id.localeCompare(b.id)),edges:project.edges.map(({id,from,to,pipe})=>({id,from,to,pipe})).sort((a,b)=>(a.from+a.to).localeCompare(b.from+b.to))});
}
export function createTemplate(id='pressure') {
 const template=TEMPLATES.find(t=>t.id===id);if(!template)throw Error('Unbekannte Vorlage.');
 const p=createProject(template.name);if(id==='pressure')return p;
 // Compact, fuel-rich channel-cooling study. Existing imported designs are never changed.
 p.design.lstarM=.5;p.design.of=2;
 const add=(nodeId,type,label,medium,section,x,y,params={})=>{p.nodes.push({id:nodeId,type,label,medium,section,x,y,params:{...DEFAULT_PARAMS[type],...params}});};
 const insert=(from,to,nodeId)=>{p.edges=p.edges.filter(e=>!(e.from===from&&e.to===to));p.edges.push({id:from+'-to-'+nodeId,from,to:nodeId},{id:nodeId+'-to-'+to,from:nodeId,to});};
 p.nodes.forEach(n=>{if(n.type==='source')n.params.pressureBar=20;if(n.x>=480)n.x+=230;if(n.x>=950)n.x+=210;});
 add('drive','shaft',id!=='turbine'?'Elektrischer Antrieb':'Turbowelle','mechanical',null,490,-170,{motorKW:id!=='turbine'?30:0});
 for(const medium of ['fuel','ox']){add(medium+'-pump','pump',medium==='ox'?'LOX Pumpe':'RP-1 Pumpe',medium,medium,480,medium==='ox'?90:350,{shaftId:'drive'});insert(medium+'-line',medium+'-valve',medium+'-pump');}
 add('regen','regen','Kühlmantel · Kanäle','fuel','fuel',930,350,{channelHeightMm:.75});insert('fuel-valve','injector','regen');
 if(id==='turbine'){
  add('drive-gas','gasSource','Treibgas · Randbedingung','gas',null,40,-420);
  add('turbine','turbine','Antriebsturbine','gas',null,490,-420,{shaftId:'drive'});
  add('exhaust','exhaust','Turbinen-Abgasdüse','gas',null,940,-420);
  p.edges.push({id:'gas-to-turbine',from:'drive-gas',to:'turbine'},{id:'turbine-to-exhaust',from:'turbine',to:'exhaust'});
 }
 if(id.startsWith('cooling-')){
  const regen=p.nodes.find(n=>n.id==='regen');regen.section='cooling';regen.x=650;regen.y=650;
  add('cool-outlet','consumer','Preburner · Brennstoffbedarf','fuel','cooling',1120,820);
  if(id==='cooling-network'){
   p.nodes.find(n=>n.id==='fuel-source').params.pressureBar=40;
   add('cool-split','branch','Kühlmittel-Abzweig','fuel','cooling',900,650);
   const e=p.edges.find(e=>e.from==='regen');e.to='cool-split';p.edges.push({id:'cool-to-main',from:'cool-split',to:'injector'},{id:'cool-to-consumer',from:'cool-split',to:'cool-outlet'});
  }else{
   p.edges.find(e=>e.to==='regen').to='injector';p.edges.find(e=>e.from==='regen').to='cool-outlet';
   add('cool-source','coolantSource','Separate RP-1-Kühlversorgung','fuel','cooling',180,650,{pressureBar:100});
   add('cool-manifold','manifold','Eintrittsmanifold','fuel','cooling',420,650,{axialPosition:1});
   p.nodes.find(n=>n.id==='cool-outlet').label='Kühlmittel-Auslass';
    p.nodes.find(n=>n.id==='cool-outlet').params={massFlowKgS:2,pressureBar:30,purpose:'other'};
   p.edges.push({id:'cool-source-manifold',from:'cool-source',to:'cool-manifold'},{id:'cool-manifold-regen',from:'cool-manifold',to:'regen'});
  }
 }
 return p;
}
export function parseProject(text) {
  if(text.length>2_000_000) throw Error('Die Projektdatei ist zu groß (max. 2 MB).');
  const p=JSON.parse(text);
  if(p?.format!=='astroforge-lite'||p.version!==1) throw Error('Keine unterstützte AstroForge-Lite-Projektdatei (Version 1).');
  if(typeof p.name!=='string'||p.name.length>120||!p.design||!Array.isArray(p.nodes)||!Array.isArray(p.edges)||p.nodes.length>100||p.edges.length>150) throw Error('Ungültige Projektstruktur.');
  for(const key of ['thrustN','pcBar','of','eps','paBar','lstarM','contractionRatio']) if(!Number.isFinite(p.design[key])) throw Error('Ungültiger Entwurfswert: '+key);
  const ids=new Set();
  for(const n of p.nodes){
    if(!n||typeof n.id!=='string'||!/^[\w-]{1,80}$/.test(n.id)||ids.has(n.id)||!Object.hasOwn(TYPES,n.type)||typeof n.label!=='string'||n.label.length>80||!['fuel','ox','gas','mechanical'].includes(n.medium)||![null,'fuel','ox','cooling'].includes(n.section)||!Number.isFinite(n.x)||!Number.isFinite(n.y)||Math.abs(n.x)>1e5||Math.abs(n.y)>1e5||!n.params||typeof n.params!=='object'||Array.isArray(n.params)) throw Error('Ungültige oder doppelte Komponente.');
    for(const value of Object.values(n.params)) if(!['number','boolean','string'].includes(typeof value)||(typeof value==='number'&&!Number.isFinite(value))) throw Error('Ungültige Komponentenparameter.');
    if(['__proto__','prototype','constructor'].includes(n.id))throw Error('Reservierte Komponenten-ID.');
    ids.add(n.id);
  }
  const edgeIds=new Set();
  for(const e of p.edges){if(!e||typeof e.id!=='string'||!/^[\w-]{1,80}$/.test(e.id)||edgeIds.has(e.id)||!ids.has(e.from)||!ids.has(e.to)||e.from===e.to)throw Error('Ungültige Verbindung.');if(e.pipe&&(!['lengthM','diameterMm','roughnessMm','k'].every(k=>Number.isFinite(e.pipe[k]))||typeof e.pipe!=='object'))throw Error('Ungültige Feedline-Parameter.');edgeIds.add(e.id);}
  return {format:p.format,version:p.version,name:p.name,design:clone(p.design),nodes:clone(p.nodes),edges:clone(p.edges),updatedAt:new Date().toISOString()};
}
export class History {
 constructor(project){this.current=clone(project);this.past=[];this.future=[];}
 commit(project){this.past.push(clone(this.current));if(this.past.length>60)this.past.shift();this.current=clone(project);this.future=[];return this.current;}
 undo(){if(this.past.length){this.future.push(this.current);this.current=this.past.pop();}return clone(this.current);}
 redo(){if(this.future.length){this.past.push(this.current);this.current=this.future.pop();}return clone(this.current);}
}
// Keep legacy line nodes readable; new workspace templates store their hydraulics on arrows.
export function compactFeedlines(project){
 const p=clone(project);
 for(const n of [...p.nodes].filter(n=>n.type==='line')){
  const incoming=p.edges.filter(e=>e.to===n.id),outgoing=p.edges.filter(e=>e.from===n.id);
  if(incoming.length!==1||outgoing.length!==1)continue;
  const a=incoming[0],b=outgoing[0];
  if(a.pipe||b.pipe)continue;
  p.edges=p.edges.filter(e=>e.id!==a.id&&e.id!==b.id);
  p.edges.push({id:a.id,from:a.from,to:b.to,pipe:clone(n.params)});
  p.nodes=p.nodes.filter(v=>v.id!==n.id);
 }
 for(const source of p.nodes.filter(n=>n.type==='source')){
  let node=source,bore=source.medium==='ox'?22:18;const seen=new Set();
  while(node&&!seen.has(node.id)&&node.type!=='injector'){
   seen.add(node.id);const edge=p.edges.find(e=>e.from===node.id);if(!edge)break;
   if(node.type==='line')bore=node.params.diameterMm;
   if(edge.pipe)bore=edge.pipe.diameterMm;else edge.pipe={lengthM:0,diameterMm:bore,roughnessMm:.01,k:0};
   node=p.nodes.find(n=>n.id===edge.to);
  }
 }
 return p;
}
