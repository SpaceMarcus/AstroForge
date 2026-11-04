/** Bounded ideal predesign, not a transient or general network solver. */
const G0 = 9.80665;
const TYPES = new Set(['source','line','valve','injector','chamber','nozzle','sensor']);
const FLUIDS = {
  fuel:{rho:810,mu:1.8e-3,tMin:288,tMax:303,label:'RP-1: konstante Screeningwerte (ρ=810 kg/m³, μ=1,8 mPa·s)'},
  ox:{rho:1140,mu:2e-4,tMin:85,tMax:95,label:'LOX: konstante Screeningwerte (ρ=1140 kg/m³, μ=0,2 mPa·s)'}
};

export async function loadThermo() {
  const response = await fetch(new URL('../thermo.json', import.meta.url));
  if (!response.ok) throw new Error('CEA-Datentabelle konnte nicht geladen werden.');
  const data = await response.json();
  if (data.format !== 'astroforge-thermo-grid' || data.version !== 1) throw new Error('Unbekanntes CEA-Datenformat.');
  return data;
}

function bracket(axis,value,name) {
  if (!Number.isFinite(value) || value < axis[0] || value > axis.at(-1)) throw new Error(`${name}: nur ${axis[0]} bis ${axis.at(-1)} im CEA-Datenbereich.`);
  let lo=0;while(lo<axis.length-2 && value>axis[lo+1]) lo++;
  return [lo,(value-axis[lo])/(axis[lo+1]-axis[lo])];
}

function thermoAt(design,data) {
  if(data?.format!=='astroforge-thermo-grid' || data.version!==1) throw new Error('CEA-Datentabelle fehlt oder ist ungültig.');
  const axes=data.axes;
  const [pi,pw]=bracket(axes.pcBar,design.pcBar,'Kammerdruck [bar]');
  const [mi,mw]=bracket(axes.of,design.of,'O/F');
  const [ei,ew]=bracket(axes.eps,design.eps,'Expansion');
  const pressureEw=Math.log(design.eps/axes.eps[ei])/Math.log(axes.eps[ei+1]/axes.eps[ei]);
  const result=[0,0,0,0];
  let logPressureRatio=0;
  for(let p=0;p<2;p++)for(let m=0;m<2;m++)for(let e=0;e<2;e++){
    const weight=(p?pw:1-pw)*(m?mw:1-mw)*(e?ew:1-ew);
    const row=data.values[((pi+p)*axes.of.length+mi+m)*axes.eps.length+ei+e];
    if(!Array.isArray(row)||row.length!==4||row.some(x=>!Number.isFinite(x)||x<=0))throw new Error('CEA-Tabelle enthält ungültige Werte.');
    row.forEach((v,i)=>result[i]+=v*weight);
    const pressureWeight=(p?pw:1-pw)*(m?mw:1-mw)*(e?pressureEw:1-pressureEw);
    logPressureRatio+=Math.log(row[3]/axes.pcBar[pi+p])*pressureWeight;
  }
  return {cstarMS:result[0],cfVac:result[1],tcK:result[2],peBar:design.pcBar*Math.exp(logPressureRatio)};
}

function inspectGraph(project,errors) {
  const nodes=project.nodes,edges=project.edges;
  if(!Array.isArray(nodes)||!Array.isArray(edges)||nodes.length>200||edges.length>300){errors.push({message:'Ungültiger oder zu großer Systemplan.'});return null;}
  const map=new Map(),incoming=new Map(),outgoing=new Map();
  const error=(node,message)=>errors.push({nodeId:node?.id,message});
  for(const n of nodes){
    if(!n||typeof n.id!=='string'||!n.id||map.has(n.id)){error(n,'Bauteil-IDs fehlen oder sind doppelt.');continue;}
    if(!TYPES.has(n.type))error(n,'Dieser Bauteiltyp wird in Lite nicht unterstützt.');
    if(!['fuel','ox','gas'].includes(n.medium))error(n,'Medium fehlt oder ist ungültig.');
    if(!n.params||typeof n.params!=='object')error(n,'Bauteilparameter fehlen.');
    if(n.section!=null && !['fuel','ox'].includes(n.section))error(n,'Unbekannte Section.');
    if(n.section && (n.medium!==n.section || !['line','valve','sensor'].includes(n.type)))error(n,'Section und Bauteilmedium passen nicht zusammen.');
    map.set(n.id,n);incoming.set(n.id,[]);outgoing.set(n.id,[]);
  }
  const edgeIds=new Set(),pairs=new Set();
  for(const e of edges){
    if(!e||!map.has(e.from)||!map.has(e.to)||e.from===e.to){errors.push({message:'Eine Verbindung hat ungültige Anschlüsse.'});continue;}
    const pair=`${e.from}\0${e.to}`;
    if(edgeIds.has(e.id)||pairs.has(pair))errors.push({nodeId:e.from,message:'Doppelte Verbindung oder Verbindungs-ID.'});
    edgeIds.add(e.id);pairs.add(pair);outgoing.get(e.from).push(e.to);incoming.get(e.to).push(e.from);
  }
  const singles={};
  for(const type of ['injector','chamber','nozzle']){
    const found=nodes.filter(n=>n?.type===type);if(found.length!==1)errors.push({message:`Genau ein Bauteil vom Typ ${type} erforderlich.`});else singles[type]=found[0];
  }
  const sources={};for(const medium of ['fuel','ox']){
    const found=nodes.filter(n=>n?.type==='source'&&n.medium===medium);
    if(found.length!==1)errors.push({message:`Genau eine ${medium==='fuel'?'Brennstoff':'Oxidator'}-Versorgung erforderlich.`});else sources[medium]=found[0];
  }
  for(const n of nodes){
    if(!map.has(n?.id))continue;
    const inc=incoming.get(n.id).length,out=outgoing.get(n.id).length;
    const expectedIn=n.type==='source'?0:n.type==='injector'?2:1,expectedOut=n.type==='nozzle'?0:1;
    if(inc!==expectedIn||out!==expectedOut)error(n,'Offene Anschlüsse oder Verzweigung: Lite benötigt zwei unverzweigte Versorgungspfade.');
    if(['injector','chamber','nozzle'].includes(n.type)&&n.medium!=='gas')error(n,'Dieses Bauteil benötigt das Medium Heißgas.');
  }
  if(errors.length)return null;
  if(outgoing.get(singles.injector.id)[0]!==singles.chamber.id||outgoing.get(singles.chamber.id)[0]!==singles.nozzle.id){errors.push({message:'Injektor, Kammer und Düse müssen direkt aufeinander folgen.'});return null;}
  const visited=new Set([singles.injector.id,singles.chamber.id,singles.nozzle.id]),paths={};
  for(const medium of ['fuel','ox']){
    const path=[],seen=new Set();let node=sources[medium];
    while(node.id!==singles.injector.id){
      if(seen.has(node.id)||visited.has(node.id)){error(node,'Schleife oder zusammengeführte Fluidpfade sind nicht unterstützt.');break;}
      if(node.medium!==medium||!['source','line','valve','sensor'].includes(node.type)){error(node,'Brennstoff- und Oxidatorpfad müssen bis zum Injektor getrennt bleiben.');break;}
      seen.add(node.id);visited.add(node.id);path.push(node);node=map.get(outgoing.get(node.id)[0]);
    }
    if(!path.some(n=>n.type==='line'))error(sources[medium],'Jeder Versorgungspfad benötigt mindestens eine Leitung als hydraulische Querschnittsreferenz.');
    paths[medium]=path;
  }
  if(visited.size!==nodes.length)errors.push({message:'Nicht angeschlossene Bauteile oder eine isolierte Schleife im Systemplan.'});
  return errors.length?null:{...singles,sources,paths};
}

function validateNumber(value,min,max,label,node,errors){
  if(!Number.isFinite(value)||value<min||value>max)errors.push({nodeId:node?.id,message:`${label}: Wert zwischen ${min} und ${max} erforderlich.`});
}

function geometryFor(design,area){
  const rt=Math.sqrt(area/Math.PI),re=rt*Math.sqrt(design.eps),rc=rt*Math.sqrt(design.contractionRatio);
  const chamberLength=design.lstarM/design.contractionRatio;
  const convergentLength=(rc-rt)/Math.tan(Math.PI/4);
  const nozzleLength=0.8*(re-rt)/Math.tan(Math.PI/12);
  const throatX=chamberLength+convergentLength;
  const contour=[{x:0,r:rc},{x:chamberLength,r:rc}];
  for(let i=1;i<=24;i++){const t=i/24;contour.push({x:chamberLength+t*convergentLength,r:rc+(rt-rc)*(3*t*t-2*t*t*t)});}
  // Cubic visual approximation with zero slope at throat; not a Rao/MoC contour.
  for(let i=1;i<=40;i++){const t=i/40;contour.push({x:throatX+t*nozzleLength,r:rt+(re-rt)*(2.6*t*t-1.6*t*t*t)});}
  return {throatRadiusM:rt,exitRadiusM:re,chamberRadiusM:rc,chamberLengthM:chamberLength,nozzleLengthM:nozzleLength,contour};
}

function evaluateFeed(path,medium,mdot,pcBar,injectorDrop,errors,warnings){
  const source=path[0],fluid=FLUIDS[medium],stations={},drops=new Map();
  const firstLine=path.find(n=>n.type==='line');let boreMm=firstLine.params.diameterMm;
  for(const node of path){
    let drop=0;
    if(node.type==='line'||node.type==='valve'){
      if(node.type==='line')boreMm=node.params.diameterMm;
      const diameter=boreMm/1000,area=Math.PI*diameter**2/4,velocity=mdot/(fluid.rho*area),dynamic=fluid.rho*velocity**2/2;
      if(node.type==='line'){
        const re=fluid.rho*velocity*diameter/fluid.mu,rough=node.params.roughnessMm/1000;
        const laminar=64/re,turbulent=(-1.8*Math.log10((rough/(3.7*diameter))**1.11+6.9/re))**-2;
        const fraction=Math.min(1,Math.max(0,(re-2300)/1700));
        const friction=re<2300?laminar:re>4000?turbulent:laminar+(turbulent-laminar)*fraction;
        drop=(friction*node.params.lengthM/diameter+node.params.k)*dynamic/1e5;
        if(re>=2300&&re<=4000)warnings.push(`${node.label||node.id}: Übergangsströmung, interpolierter Reibungsbeiwert.`);
      } else drop=node.params.k*dynamic/1e5;
      if(velocity>100)errors.push({nodeId:node.id,message:'Strömungsgeschwindigkeit über 100 m/s: außerhalb des Lite-Screeningbereichs.'});
      if(!Number.isFinite(drop))errors.push({nodeId:node.id,message:'Druckverlust nicht endlich; Leitungsparameter prüfen.'});
    }
    drops.set(node.id,drop);
  }
  let pressure=pcBar+injectorDrop;
  for(const node of [...path].reverse()){
    const drop=drops.get(node.id);pressure+=drop;
    stations[node.id]={pressureBar:pressure,temperatureK:source.params.temperatureK,massFlowKgS:mdot,dropBar:drop};
  }
  const feed={requiredBar:pressure,availableBar:source.params.pressureBar,marginBar:source.params.pressureBar-pressure,massFlowKgS:mdot};
  if(feed.marginBar<0)warnings.push(`${medium==='fuel'?'Brennstoff':'Oxidator'}: verfügbarer Versorgungsdruck reicht für den Zielbetriebspunkt nicht aus.`);
  return {feed,stations};
}

export function solveProject(project,data){
  const errors=[],warnings=[];
  if(!project||typeof project!=='object'||!project.design)return {ok:false,errors:[{message:'Kein gültiges Triebwerksprojekt.'}],warnings};
  const design=project.design;
  validateNumber(design.thrustN,100,100000,'Zielschub [N]',null,errors);
  validateNumber(design.paBar,0,1.2,'Umgebungsdruck [bar]',null,errors);
  validateNumber(design.lstarM,0.2,3,'Charakteristische Länge [m]',null,errors);
  validateNumber(design.contractionRatio,1.5,8,'Kontraktionsverhältnis',null,errors);
  let thermo;try{thermo=thermoAt(design,data);}catch(e){errors.push({message:e.message});}
  const graph=inspectGraph(project,errors);
  if(!graph||errors.length)return {ok:false,errors,warnings};
  for(const medium of ['fuel','ox']){
    const fluid=FLUIDS[medium];
    for(const node of graph.paths[medium]){
      const p=node.params;
      if(node.type==='source'){
        validateNumber(p.pressureBar,2,200,'Versorgungsdruck [bar]',node,errors);
        validateNumber(p.temperatureK,fluid.tMin,fluid.tMax,'Temperatur [K]',node,errors);
      }
      if(node.type==='line'){
        validateNumber(p.lengthM,0,100,'Leitungslänge [m]',node,errors);
        validateNumber(p.diameterMm,1,200,'Innendurchmesser [mm]',node,errors);
        validateNumber(p.roughnessMm,0,Math.min(1,p.diameterMm/20),'Rauheit [mm]',node,errors);
        validateNumber(p.k,0,10000,'Örtlicher Verlustbeiwert',node,errors);
      }
      if(node.type==='valve'){
        validateNumber(p.k,0,10000,'Ventil-Verlustbeiwert',node,errors);
        if(p.open!==true)errors.push({nodeId:node.id,message:'Geschlossenes Ventil: kein stationärer Zielmassenstrom möglich.'});
      }
      if(node.type==='sensor'&&!['pressure','temperature','massflow'].includes(p.quantity))errors.push({nodeId:node.id,message:'Unbekannte Messgröße.'});
    }
  }
  validateNumber(graph.injector.params.fuelDropBar,0,100,'Injektorverlust Brennstoff [bar]',graph.injector,errors);
  validateNumber(graph.injector.params.oxDropBar,0,100,'Injektorverlust Oxidator [bar]',graph.injector,errors);
  if(errors.length)return {ok:false,errors,warnings};
  const cf=thermo.cfVac-design.paBar/design.pcBar*design.eps;
  if(cf<=0)return {ok:false,errors:[{message:'Kein positiver idealer Schubkoeffizient für diese Randbedingungen.'}],warnings};
  const area=design.thrustN/(cf*design.pcBar*1e5),mdot=design.pcBar*1e5*area/thermo.cstarMS;
  const fuel=mdot/(1+design.of),ox=mdot-fuel;
  const fuelResult=evaluateFeed(graph.paths.fuel,'fuel',fuel,design.pcBar,graph.injector.params.fuelDropBar,errors,warnings);
  const oxResult=evaluateFeed(graph.paths.ox,'ox',ox,design.pcBar,graph.injector.params.oxDropBar,errors,warnings);
  if(errors.length)return {ok:false,errors,warnings};
  warnings.push('Idealer Vorentwurf: keine Verbrennungs-, Reibungs- oder Divergenzverluste; kein thermischer oder struktureller Nachweis.');
  warnings.push('Versorgung isotherm mit konstanten Stoffwerten; Pfaddrücke sind erforderliche Gesamtdruckbudgets am Zielbetriebspunkt, keine gelösten lokalen statischen Istdrücke. Höhenunterschiede werden nicht berücksichtigt.');
  warnings.push('CEA-Reaktanten: RP-1 bei 298,15 K und LOX bei 90,18 K. Die einstellbaren Versorgungstemperaturen sind nicht an die CEA-Thermochemie gekoppelt.');
  warnings.push(FLUIDS.fuel.label+'; '+FLUIDS.ox.label+'.');
  warnings.push('Ventilquerschnitt = Querschnitt der vorangehenden Leitung (ohne Vorgänger: erste Leitung im Pfad).');
  warnings.push('2D-Glockenkontur: glatte kubische Visualisierungsnäherung, keine Rao-/MoC-Auslegung. L* bezieht sich hier auf das zylindrische Kammervolumen.');
  if(design.paBar>thermo.peBar)warnings.push('Überexpandierte Düse: ideale anliegende Strömung angenommen; Ablösung wird in Lite nicht berechnet.');
  return {ok:true,errors,warnings,
    performance:{thrustN:design.thrustN,ispS:cf*thermo.cstarMS/G0,cstarMS:thermo.cstarMS,tcK:thermo.tcK,mdotKgS:mdot,fuelKgS:fuel,oxKgS:ox,cf},
    geometry:geometryFor(design,area),feeds:{fuel:fuelResult.feed,ox:oxResult.feed},
    stations:{...fuelResult.stations,...oxResult.stations,[graph.injector.id]:{pressureBar:design.pcBar,temperatureK:thermo.tcK,massFlowKgS:mdot,dropBar:null,fuelDropBar:graph.injector.params.fuelDropBar,oxDropBar:graph.injector.params.oxDropBar},[graph.chamber.id]:{pressureBar:design.pcBar,temperatureK:thermo.tcK,massFlowKgS:mdot,dropBar:0},[graph.nozzle.id]:{pressureBar:thermo.peBar,temperatureK:null,massFlowKgS:mdot,dropBar:null}},
    meta:{model:'Lite 2.0 · idealer stationärer Auslegungspunkt',source:data.source,domain:'LOX/RP-1 · Gleichgewicht · pc 10–80 bar · O/F 2–3,2 · ε 4–40 · CEA-Interpolation ohne Extrapolation',interpolation:'c*, Cf, Tc trilinear; log(pe/pc) linear in pc, O/F and log(eps)',sampledValidation:data.validation,chamberModel:'infinite-area',reactants:data.reactants,feedModel:'Darcy–Weisbach / Haaland, konstante Stoffwerte',pressureBasis:'feed: required total-pressure budget; local static pressure and elevation not solved',geometryModel:'smooth cubic visual bell approximation'}};
}
