import {getPair,getFluid} from './propellants.js';
import {coolingParams} from './cooling-layout.js';
import {solveLiquidNetwork} from './liquid-network.js';
import {createProject} from './state.js';
import {coolantAt,staticPressureAt,solveCooling,CHANNEL_BOUNDS} from './cooling.js';
/** Bounded ideal predesign, not a transient or general network solver. */
const G0 = 9.80665;
const TYPES = new Set(['source','line','turn','manifold','valve','injector','chamber','nozzle','sensor','pump','regen','shaft','gasSource','turbine','exhaust']);
const FLUIDS = {
  fuel:{rho:810,mu:1.8e-3,tMin:288,tMax:303,label:'RP-1: konstante Screeningwerte (ρ=810 kg/m³, μ=1,8 mPa·s)'},
  ox:{rho:1140,mu:2e-4,tMin:85,tMax:95,label:'LOX: konstante Screeningwerte (ρ=1140 kg/m³, μ=0,2 mPa·s)'}
};

export async function loadThermo() {
  const response = await fetch(new URL('../thermo.json', import.meta.url));
  if (!response.ok) throw new Error('CEA-Datentabelle konnte nicht geladen werden.');
  const data = await response.json();
  const catalogResponse = await fetch(new URL('../propellant-data.json', import.meta.url));
  if (!catalogResponse.ok) throw new Error('Treibstoff-Datenkatalog konnte nicht geladen werden.');
  data.catalog = await catalogResponse.json();
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
    if(!['fuel','ox','gas','mechanical'].includes(n.medium))error(n,'Medium fehlt oder ist ungültig.');
    if(!n.params||typeof n.params!=='object')error(n,'Bauteilparameter fehlen.');
    if(n.section!=null && !['fuel','ox','cooling'].includes(n.section))error(n,'Unbekannte Section.');
    if(n.type==='shaft'&&n.medium!=='mechanical')error(n,'Eine Welle benötigt das Medium mechanical.');
    if(n.medium==='mechanical'&&n.type!=='shaft')error(n,'Nur Wellen dürfen mechanische Knoten sein.');
    if(n.type==='regen'&&n.medium!=='fuel')error(n,'Das Kühlungsscreening ist nur im Brennstoffpfad verfügbar.');
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
    const expectedIn=['source','gasSource','shaft'].includes(n.type)?0:n.type==='injector'?2:1,expectedOut=['nozzle','exhaust','shaft'].includes(n.type)?0:1;
    if(inc!==expectedIn||out!==expectedOut)error(n,'Offene Anschlüsse oder Verzweigung: Lite benötigt zwei unverzweigte Versorgungspfade.');
    if(['injector','chamber','nozzle','gasSource','turbine','exhaust'].includes(n.type)&&n.medium!=='gas')error(n,'Dieses Bauteil benötigt das Medium Heißgas.');
  }
  if(errors.length)return null;
  if(outgoing.get(singles.injector.id)[0]!==singles.chamber.id||outgoing.get(singles.chamber.id)[0]!==singles.nozzle.id){errors.push({message:'Injektor, Kammer und Düse müssen direkt aufeinander folgen.'});return null;}
  const shafts=nodes.filter(n=>n.type==='shaft');
  const linked=nodes.filter(n=>['pump','turbine'].includes(n.type));
  for(const node of linked)if(!shafts.some(s=>s.id===node.params.shaftId))error(node,'Pumpe/Turbine benötigt eine gültige Wellenzuordnung.');
  for(const shaft of shafts)if(!linked.some(n=>n.params.shaftId===shaft.id))error(shaft,'Welle ist keiner Pumpe oder Turbine zugeordnet.');
  const visited=new Set([singles.injector.id,singles.chamber.id,singles.nozzle.id,...shafts.map(n=>n.id)]),paths={};
  for(const medium of ['fuel','ox']){
    const path=[],seen=new Set();let node=sources[medium];
    while(node.id!==singles.injector.id){
      if(seen.has(node.id)||visited.has(node.id)){error(node,'Schleife oder zusammengeführte Fluidpfade sind nicht unterstützt.');break;}
      if(node.medium!==medium||!['source','line','turn','manifold','valve','sensor','pump','regen'].includes(node.type)){error(node,'Brennstoff- und Oxidatorpfad müssen bis zum Injektor getrennt bleiben.');break;}
      seen.add(node.id);visited.add(node.id);path.push(node);node=map.get(outgoing.get(node.id)[0]);
    }
    if(!path.some(n=>n.type==='line'))error(sources[medium],'Jeder Versorgungspfad benötigt mindestens eine Leitung als hydraulische Querschnittsreferenz.');
    paths[medium]=path;
  }
  let auxiliary=null;
  const auxNodes=nodes.filter(n=>['gasSource','turbine','exhaust'].includes(n.type));
  if(auxNodes.length){
    const gasSource=auxNodes.filter(n=>n.type==='gasSource'),turbines=auxNodes.filter(n=>n.type==='turbine'),exhausts=auxNodes.filter(n=>n.type==='exhaust');
    if(gasSource.length!==1||turbines.length!==1||exhausts.length!==1)errors.push({message:'Zusatzgas benötigt genau eine Gasquelle, eine Turbine und eine Abgasdüse.'});
    else if(outgoing.get(gasSource[0].id)[0]!==turbines[0].id||outgoing.get(turbines[0].id)[0]!==exhausts[0].id)errors.push({message:'Zusatzgas muss getrennt als Gasquelle → Turbine → Abgasdüse verbunden sein.'});
    else{auxiliary={source:gasSource[0],turbine:turbines[0],exhaust:exhausts[0]};auxNodes.forEach(n=>visited.add(n.id));}
  }
  if(visited.size!==nodes.length)errors.push({message:'Nicht angeschlossene Bauteile oder eine isolierte Schleife im Systemplan.'});
  return errors.length?null:{...singles,sources,paths,shafts,auxiliary};
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

function evaluateFeed(path,medium,mdot,pcBar,injectorDrop,errors,warnings,cycle,context=null,fluids=FLUIDS){
  const source=path[0],fluid=fluids[medium],stations={},drops=new Map(),temperatures=new Map(),dynamicPressures=new Map();
  let temperature=source.params.temperatureK;
  const firstLine=path.find(n=>n.type==='line');let boreMm=firstLine.params.diameterMm;
  for(const node of path){
    temperatures.set(node.id,temperature);
    const localPressure=context?.pressures[node.id]??pcBar+injectorDrop+5;
    const localBore=['line','turn','manifold'].includes(node.type)?node.params.diameterMm:boreMm;
    const propertyPressure=context?staticPressureAt(context.data,temperature,localPressure,Math.PI*(localBore/1000)**2/4,mdot):localPressure;
    const liquid=context?coolantAt(context.data,temperature,propertyPressure):null;
    const localFluid=liquid?{rho:liquid.rhoKgM3,mu:liquid.muPaS}:fluid;
    dynamicPressures.set(node.id,mdot**2/(2*localFluid.rho*(Math.PI*(localBore/1000)**2/4)**2)/1e5);
    let drop=0;
    if(['line','turn','manifold','valve'].includes(node.type)){
      if(node.type==='line')boreMm=node.params.diameterMm;
      const diameter=localBore/1000,area=Math.PI*diameter**2/4,velocity=mdot/(localFluid.rho*area),dynamic=localFluid.rho*velocity**2/2;
      if(node.type==='line'){
        const re=localFluid.rho*velocity*diameter/localFluid.mu,rough=node.params.roughnessMm/1000;
        const laminar=64/re,turbulent=(-1.8*Math.log10((rough/(3.7*diameter))**1.11+6.9/re))**-2;
        const fraction=Math.min(1,Math.max(0,(re-2300)/1700));
        const friction=re<2300?laminar:re>4000?turbulent:laminar+(turbulent-laminar)*fraction;
        drop=(friction*node.params.lengthM/diameter+node.params.k)*dynamic/1e5;
        if(re>=2300&&re<=4000)warnings.push(`${node.label||node.id}: Übergangsströmung, interpolierter Reibungsbeiwert.`);
      } else drop=node.params.k*dynamic/1e5;
      if(velocity>100)errors.push({nodeId:node.id,message:'Strömungsgeschwindigkeit über 100 m/s: außerhalb des Lite-Screeningbereichs.'});
      if(!Number.isFinite(drop))errors.push({nodeId:node.id,message:'Druckverlust nicht endlich; Leitungsparameter prüfen.'});
    }
    if(node.type==='pump'){
      drop=-node.params.riseBar;
      const hydraulicPowerKW=mdot*node.params.riseBar*1e5/localFluid.rho/1000;
      cycle.pumps.push({nodeId:node.id,shaftId:node.params.shaftId,pressureRiseBar:node.params.riseBar,hydraulicPowerKW,shaftPowerKW:hydraulicPowerKW/node.params.efficiency,massFlowKgS:mdot});
    }
    if(node.type==='regen'&&node.params.mode==='channels'){
      const result=solveCooling({params:context.project?coolingParams(context.project,node):node.params,geometry:context.geometry,design:context.design,thermo:context.thermo,data:context.data,massFlowKgS:mdot,inletTemperatureK:temperature,inletPressureBar:localPressure});
      cycle.cooling.push({nodeId:node.id,...result});drop=result.dropBar;temperature=result.outletTemperatureK;
      warnings.push(...result.warnings);if(!result.feasible)warnings.push('Kühlkanal: zulässige Wandtemperatur überschritten.');
    }
    if(node.type==='regen'&&node.params.mode!=='channels'){
      drop=node.params.dropBar;
      const outletTemperature=temperature+node.params.heatKW*1000/(mdot*node.params.cpJkgK);
      cycle.cooling.push({nodeId:node.id,heatKW:node.params.heatKW,dropBar:drop,cpJkgK:node.params.cpJkgK,inletTemperatureK:temperature,outletTemperatureK:outletTemperature,massFlowKgS:mdot});
      if(outletTemperature>650)errors.push({nodeId:node.id,message:'Kühlmittel über 650 K: außerhalb des begrenzten Wärmebilanz-Screenings.'});
      temperature=outletTemperature;
      if(fluid.minPressureBar&&!context&&(temperature<fluid.tMin||temperature>fluid.tMax))errors.push({nodeId:node.id,message:`${fluid.label}: Wärmebilanz verlässt den Stoff-Screeningbereich ${fluid.tMin}–${fluid.tMax} K.`});
    }
    drops.set(node.id,drop);
  }
  let pressure=pcBar+injectorDrop;
  for(const node of [...path].reverse()){
    const drop=drops.get(node.id);pressure+=drop;
    if(pressure<=0)errors.push({nodeId:node.id,message:'Nicht positives Druckbudget: feste Pumpendruckerhöhung überbestimmt diesen Zielentwurf. Druckerhöhung reduzieren.'});
    if(fluid.minPressureBar&&!context&&Math.min(pressure,pressure-drop)-dynamicPressures.get(node.id)<fluid.minPressureBar)errors.push({nodeId:node.id,message:`${fluid.label}: erforderlicher statischer Druck liegt unter der einphasigen Screeninggrenze (${fluid.minPressureBar} bar).`});
    stations[node.id]={pressureBar:pressure,temperatureK:temperatures.get(node.id),massFlowKgS:mdot,dropBar:drop};
  }
  const feed={requiredBar:pressure,availableBar:source.params.pressureBar,marginBar:source.params.pressureBar-pressure,massFlowKgS:mdot};
  if(feed.marginBar<0)warnings.push(`${medium==='fuel'?'Brennstoff':'Oxidator'}: verfügbarer Versorgungsdruck reicht für den Zielbetriebspunkt nicht aus.`);
  return {feed,stations};
}

function validateExtended(graph,design,errors){
  const check=(node,key,min,max,label=key)=>validateNumber(node.params[key],min,max,label,node,errors);
  for(const path of Object.values(graph.paths))for(const n of path){
    if(n.type==='pump'){check(n,'riseBar',.01,150,'Pumpendruckerhöhung [bar]');check(n,'efficiency',.05,1,'Pumpenwirkungsgrad');}
    if(n.type==='regen'&&n.params.mode!=='channels'){if(n.params.mode!==undefined&&n.params.mode!=='lumped')errors.push({nodeId:n.id,message:'Unbekanntes Kühlungsmodell.'});check(n,'heatKW',0,5000,'Aufgeprägte Wärme [kW]');check(n,'dropBar',0,100,'Kühldruckverlust [bar]');check(n,'cpJkgK',100,10000,'Kühlmittel-cp [J/(kg K)]');}
  }
  const channelNodes=Object.values(graph.paths).flat().filter(n=>n.type==='regen'&&n.params.mode==='channels');
  if(channelNodes.length>1)errors.push({message:'Maximal eine geometriegekoppelte Kanalkühlung ist erlaubt.'});
  for(const n of channelNodes)for(const [key,[min,max]] of Object.entries(CHANNEL_BOUNDS)){check(n,key,min,max,key);if(['stations','channelCount'].includes(key)&&!Number.isInteger(n.params[key]))errors.push({nodeId:n.id,message:key+' muss ganzzahlig sein.'});}
  for(const n of graph.shafts){check(n,'efficiency',.05,1,'Mechanischer Wirkungsgrad');check(n,'rpm',100,200000,'Drehzahl [rpm]');check(n,'motorKW',0,10000,'Antriebsleistung an der Welle [kW]');}
  if(graph.auxiliary){
    const {source:s,turbine:t,exhaust:e}=graph.auxiliary;
    check(s,'pressureBar',.1,200,'Treibgas-Gesamtdruck [bar]');check(s,'temperatureK',200,2000,'Treibgas-Gesamttemperatur [K]');check(s,'massFlowKgS',.001,10,'Zusatzgas-Massenstrom [kg/s]');check(s,'cpJkgK',500,10000,'Treibgas-cp [J/(kg K)]');check(s,'gamma',1.05,1.67,'Treibgas-gamma');
    check(t,'outletBar',.01,200,'Turbinen-Austrittsgesamtdruck [bar]');check(t,'efficiency',.05,1,'Turbinenwirkungsgrad');check(e,'exitBar',.001,200,'Abgas-Austrittsdruck [bar]');check(e,'efficiency',.05,1,'Düsenwirkungsgrad');
    if(!(s.params.pressureBar>t.params.outletBar&&t.params.outletBar>e.params.exitBar))errors.push({nodeId:t.id,message:'Zusatzgas benötigt Quelle > Turbinenaustritt > Düsen-Austrittsdruck.'});
    if(t.params.outletBar<=design.paBar)errors.push({nodeId:e.id,message:'Abgasdüse benötigt einen Eintrittsgesamtdruck oberhalb des Umgebungsdrucks.'});
  }
}

function evaluateCycle(graph,design,mdot,cycle,warnings,errors){
  const stations={};
  // NASA power-turbine/nozzle energy relations; constant cp and gamma.
  // https://www.grc.nasa.gov/www/k-12/airplane/powtrbth.html
  // https://www.grc.nasa.gov/WWW/K-12/airplane/nozzleh.html
  if(graph.auxiliary){
    const {source:s,turbine:t,exhaust:e}=graph.auxiliary,sp=s.params,tp=t.params,ep=e.params;
    const exponent=(sp.gamma-1)/sp.gamma;
    const turbineDeltaT=tp.efficiency*sp.temperatureK*(1-(tp.outletBar/sp.pressureBar)**exponent);
    const outletTemperatureK=sp.temperatureK-turbineDeltaT;
    const powerKW=sp.massFlowKgS*sp.cpJkgK*turbineDeltaT/1000;
    cycle.turbines.push({nodeId:t.id,shaftId:tp.shaftId,inletPressureBar:sp.pressureBar,outletPressureBar:tp.outletBar,inletTemperatureK:sp.temperatureK,outletTemperatureK,massFlowKgS:sp.massFlowKgS,powerKW});
    const nozzleDeltaT=ep.efficiency*outletTemperatureK*(1-(ep.exitBar/tp.outletBar)**exponent);
    const exitTemperatureK=outletTemperatureK-nozzleDeltaT;
    const exitVelocityMS=Math.sqrt(2*sp.cpJkgK*nozzleDeltaT);
    const gasConstant=sp.cpJkgK*(sp.gamma-1)/sp.gamma;
    const exitDensity=ep.exitBar*1e5/(gasConstant*exitTemperatureK);
    const exitAreaM2=sp.massFlowKgS/(exitDensity*exitVelocityMS);
    const thrustN=sp.massFlowKgS*exitVelocityMS+(ep.exitBar-design.paBar)*1e5*exitAreaM2;
    if(!Number.isFinite(thrustN)||thrustN<0)errors.push({nodeId:e.id,message:'Abgasdüsenmodell ergibt keinen gültigen positiven Schub. Druckverhältnis prüfen.'});
    const totalMassFlowKgS=mdot+sp.massFlowKgS,systemThrustN=design.thrustN+thrustN;
    cycle.auxiliary={sourceId:s.id,turbineId:t.id,exhaustId:e.id,massFlowKgS:sp.massFlowKgS,exitPressureBar:ep.exitBar,exitTemperatureK,exitVelocityMS,exitAreaM2,thrustN,systemThrustN,totalMassFlowKgS,systemIspS:systemThrustN/(totalMassFlowKgS*G0)};
    stations[s.id]={pressureBar:sp.pressureBar,temperatureK:sp.temperatureK,massFlowKgS:sp.massFlowKgS,dropBar:0};
    stations[t.id]={pressureBar:sp.pressureBar,temperatureK:sp.temperatureK,massFlowKgS:sp.massFlowKgS,dropBar:sp.pressureBar-tp.outletBar};
    stations[e.id]={pressureBar:ep.exitBar,temperatureK:exitTemperatureK,massFlowKgS:sp.massFlowKgS,dropBar:null};
    warnings.push('Treibgas ist eine separat versorgte Randbedingung: kein Gasgenerator, keine Treibstoffabzweigung und keine Preburnerchemie. Der zusätzliche Gasverbrauch wird nur im System-Isp berücksichtigt.');
    warnings.push('Turbine/Abgasdüse: kalorisch ideales Gas mit konstantem cp und gamma; axial gleichgerichteter Zusatzschub, Austrittsfläche aus Kontinuität dimensioniert. Keine Kennfeld-, Abströmwinkel- oder Ablösungsrechnung.');
    if(ep.exitBar<design.paBar)warnings.push('Abgasdüse überexpandiert: Druckschub enthalten, anliegende Strömung angenommen.');
  }
  for(const shaft of graph.shafts){
    const p=shaft.params,requiredPowerKW=cycle.pumps.filter(n=>n.shaftId===shaft.id).reduce((sum,n)=>sum+n.shaftPowerKW,0);
    const turbinePowerKW=cycle.turbines.filter(n=>n.shaftId===shaft.id).reduce((sum,n)=>sum+n.powerKW,0);
    const availablePowerKW=p.motorKW+turbinePowerKW*p.efficiency,balanceKW=availablePowerKW-requiredPowerKW;
    const omega=p.rpm*2*Math.PI/60,feasible=balanceKW>=-1e-9;
    cycle.shafts.push({nodeId:shaft.id,rpm:p.rpm,efficiency:p.efficiency,motorKW:p.motorKW,turbinePowerKW,availablePowerKW,requiredPowerKW,balanceKW,requiredTorqueNm:requiredPowerKW*1000/omega,availableTorqueNm:availablePowerKW*1000/omega,feasible});
    if(!feasible)warnings.push(`${shaft.label||shaft.id}: Wellenleistung reicht für die vorgegebene Pumpenarbeit nicht aus. Zielbetriebspunkt ist damit nicht erfüllbar.`);
  }
  if(cycle.pumps.length)warnings.push('Pumpen: inkompressible Druckarbeit ṁ·Δp/(ρ·η), feste Druckerhöhung. Kein Kennfeld, NPSH-/Kavitationsnachweis oder Drehzahl-Betriebspunkt; keine Pumpenerwärmung.');
  if(cycle.shafts.length)warnings.push('Wellenbilanz ist ein Leistungsbudget bei vorgegebener Drehzahl, keine automatisch geschlossene Drehmomentgleichung. Motorleistung gilt bereits an der Welle; mechanischer Wirkungsgrad wirkt auf Turbinenleistung.');
  if(cycle.cooling.some(c=>c.mode!=='channels'))warnings.push('Regenerativblock: aufgeprägte Wärme mit ΔT=Q/(ṁ·cp) und vorgegebenem Druckverlust. Keine Wandtemperatur, Kanalgeometrie oder thermische Freigabe; Fluidwerte bleiben trotz Erwärmung konstant. Die Wärmequelle ist extern aufgeprägt, ohne Energieabschluss mit Brennkammer oder Hauptdüse.');
  return stations;
}

function solveExpandedProject(project,data,coolingData,topology=project){
  const errors=[],warnings=[];
  if(!project||typeof project!=='object'||!project.design)return {ok:false,errors:[{message:'Kein gültiges Triebwerksprojekt.'}],warnings};
  const design=project.design,fluids=data?.fluids||FLUIDS;
  validateNumber(design.thrustN,100,100000,'Zielschub [N]',null,errors);
  validateNumber(design.paBar,0,1.2,'Umgebungsdruck [bar]',null,errors);
  validateNumber(design.lstarM,0.2,3,'Charakteristische Länge [m]',null,errors);
  validateNumber(design.contractionRatio,1.5,8,'Kontraktionsverhältnis',null,errors);
  let thermo;try{thermo=thermoAt(design,data);}catch(e){errors.push({message:e.message});}
  const graph=inspectGraph(project,errors);
  if(!graph||errors.length)return {ok:false,errors,warnings};
  for(const medium of ['fuel','ox']){
    const fluid=fluids[medium];
    for(const node of graph.paths[medium]){
      const p=node.params;
      if(node.type==='source'){
        validateNumber(p.pressureBar,2,200,'Versorgungsdruck [bar]',node,errors);
        validateNumber(p.temperatureK,fluid.tMin,fluid.tMax,'Temperatur [K]',node,errors);
        if(fluid.minPressureBar&&p.pressureBar<fluid.minPressureBar)errors.push({nodeId:node.id,message:`${fluid.label}: Versorgungsdruck unter der einphasigen Screeninggrenze (${fluid.minPressureBar} bar).`});
      }
      if(node.type==='line'){
        validateNumber(p.lengthM,0,100,'Leitungslänge [m]',node,errors);
        validateNumber(p.diameterMm,1,200,'Innendurchmesser [mm]',node,errors);
        validateNumber(p.roughnessMm,0,Math.min(1,p.diameterMm/20),'Rauheit [mm]',node,errors);
        validateNumber(p.k,0,10000,'Örtlicher Verlustbeiwert',node,errors);
      }
      if(['turn','manifold'].includes(node.type)){validateNumber(p.diameterMm,1,200,'Bezugsdurchmesser [mm]',node,errors);validateNumber(p.k,0,10000,'Örtlicher Verlustbeiwert',node,errors);}
      if(node.type==='valve'){
        validateNumber(p.k,0,10000,'Ventil-Verlustbeiwert',node,errors);
        if(p.open!==true)errors.push({nodeId:node.id,message:'Geschlossenes Ventil: kein stationärer Zielmassenstrom möglich.'});
      }
      if(node.type==='sensor'&&!['pressure','temperature','massflow'].includes(p.quantity))errors.push({nodeId:node.id,message:'Unbekannte Messgröße.'});
    }
  }
  validateNumber(graph.injector.params.fuelDropBar,0,100,'Injektorverlust Brennstoff [bar]',graph.injector,errors);
  validateNumber(graph.injector.params.oxDropBar,0,100,'Injektorverlust Oxidator [bar]',graph.injector,errors);
  validateExtended(graph,design,errors);
  if(errors.length)return {ok:false,errors,warnings};
  const cf=thermo.cfVac-design.paBar/design.pcBar*design.eps;
  if(cf<=0)return {ok:false,errors:[{message:'Kein positiver idealer Schubkoeffizient für diese Randbedingungen.'}],warnings};
  const area=design.thrustN/(cf*design.pcBar*1e5),mdot=design.pcBar*1e5*area/thermo.cstarMS;
  const fuel=mdot/(1+design.of),ox=mdot-fuel;
  const cycle={pumps:[],cooling:[],turbines:[],shafts:[]};
  let fuelResult;
  const geometry=geometryFor(design,area),channels=graph.paths.fuel.some(n=>n.type==='regen'&&n.params.mode==='channels');
  try{
    if(channels){
      const pressures=Object.fromEntries(graph.paths.fuel.map(n=>[n.id,coolingData?.coolant?.axes?.pressureBar?.at(-1)??200]));let converged=false;
      for(let iteration=0;iteration<60;iteration++){
        const trialCycle={pumps:[],cooling:[]},trialWarnings=[],trialErrors=[];
        const trial=evaluateFeed(graph.paths.fuel,'fuel',fuel,design.pcBar,graph.injector.params.fuelDropBar,trialErrors,trialWarnings,trialCycle,{pressures,data:coolingData,geometry,design,thermo,project:topology},fluids);
        if(trialErrors.length){errors.push(...trialErrors);break;}
        let residual=0;for(const [id,s] of Object.entries(trial.stations)){residual=Math.max(residual,Math.abs(pressures[id]-s.pressureBar));pressures[id]=.5*(pressures[id]+s.pressureBar);}
        if(residual<1e-5){fuelResult=trial;cycle.pumps.push(...trialCycle.pumps);cycle.cooling.push(...trialCycle.cooling);warnings.push(...trialWarnings);converged=true;break;}
      }
      if(!converged&&!errors.length)errors.push({message:'Gekoppeltes Kühlungs-Druckbudget konvergiert nicht.'});
      if(converged)for(const station of Object.values(fuelResult.stations))coolantAt(coolingData,station.temperatureK,station.pressureBar);
      warnings.push('Kanalkühlung: stationäres 1D-Kanalmodell mit gewählter Strömungsrichtung und ausgewiesenen Stoffdaten. Bartz, rechteckige Kanäle und Rippen; keine Strahlung, Verkokung, Siedung oder Strukturlebensdauer. CEA-Gaszustand bleibt feste Randbedingung; Bartz mit frozen-Kammertransport und konstantem frozen-gamma, isentroper lokaler Machzahl und Recoverytemperatur; kein chemisch-thermischer Kreislaufschluss.');
    }else fuelResult=evaluateFeed(graph.paths.fuel,'fuel',fuel,design.pcBar,graph.injector.params.fuelDropBar,errors,warnings,cycle,null,fluids);
  }catch(e){errors.push({nodeId:graph.paths.fuel.find(n=>n.params.mode==='channels')?.id,message:e.message});}
  if(errors.length)return {ok:false,errors,warnings};
  const oxResult=evaluateFeed(graph.paths.ox,'ox',ox,design.pcBar,graph.injector.params.oxDropBar,errors,warnings,cycle,null,fluids);
  const auxiliaryStations=evaluateCycle(graph,design,mdot,cycle,warnings,errors);
  if(errors.length)return {ok:false,errors,warnings};
  warnings.push('Idealer Vorentwurf: keine Verbrennungs-, Reibungs- oder Divergenzverluste; kein thermischer oder struktureller Nachweis.');
  warnings.push((channels?'Brennstoff mit temperatur- und druckabhängigen Ersatzstoffwerten; Oxidator mit konstanten Stoffwerten, ':'Versorgung mit konstanten Stoffwerten, ')+ ' außerhalb eines Kühlblocks isotherm; Pfaddrücke sind erforderliche Gesamtdruckbudgets am Zielbetriebspunkt, keine gelösten lokalen statischen Istdrücke. Höhenunterschiede werden nicht berücksichtigt.');
  warnings.push(`CEA-Reaktanten: ${getPair(design).label}; Tabellen-Eintrittszustände siehe Datenquelle. Die einstellbaren Versorgungstemperaturen sind nicht an die CEA-Thermochemie gekoppelt.`);
  warnings.push((channels?`Kühlmittel: ${getPair(design).fuel==='rp1'?'n-Dodecan als RP-1-Ersatz':'Ethanol'}, einphasig und nur innerhalb der Tabelle`:fluids.fuel.label)+'; '+fluids.ox.label+'.');
  warnings.push('Ventilquerschnitt = Querschnitt der vorangehenden Leitung (ohne Vorgänger: erste Leitung im Pfad).');
  warnings.push('2D-Glockenkontur: glatte kubische Visualisierungsnäherung, keine Rao-/MoC-Auslegung. L* bezieht sich hier auf das zylindrische Kammervolumen.');
  if(design.paBar>thermo.peBar)warnings.push('Überexpandierte Düse: ideale anliegende Strömung angenommen; Ablösung wird in Lite nicht berechnet.');
  return {ok:true,errors,warnings,cycle,
    performance:{thrustN:design.thrustN,ispS:cf*thermo.cstarMS/G0,cstarMS:thermo.cstarMS,tcK:thermo.tcK,mdotKgS:mdot,fuelKgS:fuel,oxKgS:ox,cf},
    geometry,feeds:{fuel:fuelResult.feed,ox:oxResult.feed},
    stations:{...fuelResult.stations,...oxResult.stations,...auxiliaryStations,[graph.injector.id]:{pressureBar:design.pcBar,temperatureK:thermo.tcK,massFlowKgS:mdot,dropBar:null,fuelDropBar:graph.injector.params.fuelDropBar,oxDropBar:graph.injector.params.oxDropBar},[graph.chamber.id]:{pressureBar:design.pcBar,temperatureK:thermo.tcK,massFlowKgS:mdot,dropBar:0},[graph.nozzle.id]:{pressureBar:thermo.peBar,temperatureK:null,massFlowKgS:mdot,dropBar:null}},
    meta:{model:'Lite 2.0 · idealer stationärer Auslegungspunkt',source:data.source,feedFluids:Object.fromEntries(Object.entries(fluids).map(([medium,fluid])=>[medium,{...fluid,source:fluid.source||'Legacy constant screening properties; see MODELS.md'}])),coolantSource:channels?coolingData?.coolant?.source:null,domain:`${getPair(design).label} · Gleichgewicht · pc ${data.axes.pcBar[0]}–${data.axes.pcBar.at(-1)} bar · O/F ${data.axes.of[0]}–${data.axes.of.at(-1)} · ε ${data.axes.eps[0]}–${data.axes.eps.at(-1)} · CEA-Interpolation ohne Extrapolation`,propellantPair:getPair(design).id,interpolation:'c*, Cf, Tc trilinear; log(pe/pc) linear in pc, O/F and log(eps)',sampledValidation:data.validation,chamberModel:'infinite-area',reactants:data.reactants,feedModel:channels?'Darcy–Weisbach / Haaland; fuel T/p table, constant oxidizer screening properties':'Darcy–Weisbach / Haaland, konstante Stoffwerte',coolingModel:channels?'1D selectable flow and coverage, frozen chamber transport/Bartz, fixed gas boundary':null,coolingSource:channels?coolingData.source:null,pressureBasis:channels?'feed: required total-pressure budget; cooling: static pressure march plus dynamic conversion, no elevation':'feed: required total-pressure budget; local static pressure and elevation not solved',geometryModel:'smooth cubic visual bell approximation',formulaSources:[{model:'Pump power',url:'https://www.energy.gov/sites/default/files/2014/05/f16/pump.pdf'},{model:'Ideal-gas turbine work',url:'https://www.grc.nasa.gov/www/k-12/airplane/powtrbth.html'},{model:'Nozzle expansion',url:'https://www.grc.nasa.gov/WWW/K-12/airplane/nozzleh.html'},{model:'Thrust and specific impulse',url:'https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/specific-impulse/'}]}};
}


export function solveProject(project,data,coolingData){
 try{
  const pair=getPair(project?.design);
  if(pair.id!=='lox-rp1'){
   const selected=data?.catalog?.pairs?.[pair.id];
   if(!selected||selected.pairId!==pair.id||!selected.fluids?.fuel||!selected.fluids?.ox)throw Error('Keine passenden Rechen- und Stoffdaten für '+pair.label+'.');
   coolingData=data.catalog.cooling?.[pair.id];data={...selected,catalog:data.catalog};
  }
  if(project?.nodes?.some(n=>n?.type==='regen'&&n.params?.mode==='channels')){
   if(!pair.channelCooling)throw Error('Kühlkanalmodell für '+pair.label+' noch nicht verfügbar. Wärmebilanzmodell oder Entwurf ohne Kanalkühlung verwenden.');
   if(!coolingData)throw Error('Passende Kühlstoffdaten fehlen für '+pair.label+'.');
  }
 }catch(e){return {ok:false,errors:[{message:e.message}],warnings:[]};}

 if(!Array.isArray(project?.nodes)||!Array.isArray(project?.edges))return solveExpandedProject(project,data,coolingData);
 if(project.nodes.filter(n=>n?.type==='regen'&&n.params?.mode==='channels').length>1||project.nodes.some(n=>['branch','restriction','consumer','coolantSource'].includes(n?.type)||n?.type==='manifold'&&project.edges.filter(e=>e?.from===n.id).length>1))return solveBranchedProject(project,data,coolingData);
 const expanded={...project,nodes:[...project.nodes],edges:[]},mapping=new Map();
 for(const e of project.edges){
  if(!e){expanded.edges.push(e);continue;}
  const from=project.nodes.find(n=>n?.id===e.from);
  if(!e.pipe){expanded.edges.push(e);continue;}
  if(!['fuel','ox'].includes(from?.medium))return {ok:false,errors:[{edgeId:e.id,message:'Feedline-Druckverluste werden derzeit nur für flüssigen Brennstoff und Oxidator berechnet.'}],warnings:[]};
  // Internal IDs cannot collide with persisted user IDs (which exclude colons).
  const id='pipe:'+e.id;mapping.set(id,e.id);
  expanded.nodes.push({id,type:'line',label:'Feedline',medium:from.medium,section:null,params:e.pipe});
  expanded.edges.push({...e,to:id},{id:'pipe-out:'+e.id,from:id,to:e.to});
 }
 const r=solveExpandedProject(expanded,data,coolingData,project);
 r.errors=(r.errors||[]).map(e=>mapping.has(e.nodeId)?{...e,nodeId:undefined,edgeId:mapping.get(e.nodeId)}:e);
 if(r.ok){
  r.edgeStates={};
  for(const [id,edgeId] of mapping){const v=r.stations[id];r.edgeStates[edgeId]={...v,outletPressureBar:v.pressureBar-v.dropBar};delete r.stations[id];}
  for(const e of project.edges){
   if(r.edgeStates[e.id])continue;
   const from=project.nodes.find(n=>n.id===e.from),to=project.nodes.find(n=>n.id===e.to),a=r.stations[from.id],b=r.stations[to.id];
   const cooling=r.cycle.cooling.find(c=>c.nodeId===from.id),turbine=r.cycle.turbines.find(t=>t.nodeId===from.id),liquid=['fuel','ox'].includes(from.medium);
   const pressureBar=liquid?(to.type==='injector'?project.design.pcBar+to.params[from.medium==='fuel'?'fuelDropBar':'oxDropBar']:b?.pressureBar):(turbine?.outletPressureBar??a?.pressureBar);
   const temperatureK=cooling?.outletTemperatureK??turbine?.outletTemperatureK??a?.temperatureK;
   r.edgeStates[e.id]={pressureBar,outletPressureBar:pressureBar,temperatureK,massFlowKgS:a?.massFlowKgS,dropBar:0};
  }
 }
 return r;
}


function solveBranchedProject(project,data,coolingData){
 const errors=[],warnings=[];
 try{
  if(!Array.isArray(project.edges)||project.nodes.length>100||project.edges.length>150)throw Error('Ungültiges oder zu großes Netz.');
  const ids=new Set(),edgeIds=new Set();for(const n of project.nodes){if(!n?.id||ids.has(n.id)||!n.params)throw Error('Ungültige oder doppelte Bauteile.');if(n.section!=null&&!['fuel','ox','cooling'].includes(n.section))throw Error('Unbekannte Section.');ids.add(n.id);}
  for(const e of project.edges){if(!e?.id||edgeIds.has(e.id)||!ids.has(e.from)||!ids.has(e.to)||e.from===e.to)throw Error('Ungültige oder doppelte Verbindung.');edgeIds.add(e.id);}
  const singles={};for(const type of ['injector','chamber','nozzle']){const found=project.nodes.filter(n=>n.type===type);if(found.length!==1)throw Error('Genau ein '+type+' erforderlich.');singles[type]=found[0];if(found[0].medium!=='gas')throw Error('Triebwerksbauteile benötigen Heißgas als Medium.');}
  if(!project.edges.some(e=>e.from===singles.injector.id&&e.to===singles.chamber.id)||!project.edges.some(e=>e.from===singles.chamber.id&&e.to===singles.nozzle.id))throw Error('Injektor, Kammer und Düse müssen direkt verbunden sein.');
  const reference=createProject();reference.design=project.design;reference.nodes.find(n=>n.type==='injector').params=singles.injector.params;
  for(const n of reference.nodes)if(n.type==='source')n.params.temperatureK=getFluid(getPair(project.design)[n.medium]).temperatureK;
  // This reference computes only core thermochemistry/geometry; its artificial feed must not limit the real network.
  for(const n of reference.nodes)if(n.type==='line')Object.assign(n.params,{diameterMm:200,lengthM:0,k:0});else if(n.type==='valve')n.params.k=0;
  const base=solveExpandedProject(reference,data,coolingData);if(!base.ok)return base;
  const channelNodes=project.nodes.filter(n=>n.type==='regen'&&n.params.mode==='channels');
  for(let i=0;i<channelNodes.length;i++)for(let j=i+1;j<channelNodes.length;j++){const a=coolingParams(project,channelNodes[i]),b=coolingParams(project,channelNodes[j]);if(Math.min(a.coolingEnd??1,b.coolingEnd??1)-Math.max(a.coolingStart??0,b.coolingStart??0)>1e-8)throw Error('Kühlstrecken überlappen: Mehrfachbelegung derselben Wandfläche ist noch nicht modelliert. Start/Ende der Strecken trennen.');}
  const net=solveLiquidNetwork(project,base,coolingData,data.fluids||FLUIDS),cycle={...net.cycles,turbines:[],shafts:[],consumers:net.consumers},shafts=project.nodes.filter(n=>n.type==='shaft');
  const aux=project.nodes.filter(n=>['gasSource','turbine','exhaust'].includes(n.type));let auxiliary=null;
  if(aux.length){const source=aux.find(n=>n.type==='gasSource'),turbine=aux.find(n=>n.type==='turbine'),exhaust=aux.find(n=>n.type==='exhaust');if(aux.length!==3||!source||!turbine||!exhaust||!project.edges.some(e=>e.from===source.id&&e.to===turbine.id)||!project.edges.some(e=>e.from===turbine.id&&e.to===exhaust.id))throw Error('Treibgaszweig benötigt Quelle → Turbine → Abgasdüse.');auxiliary={source,turbine,exhaust};}
  const allowed=new Set(['source','coolantSource','line','valve','sensor','pump','regen','turn','manifold','branch','restriction','consumer','injector','chamber','nozzle','shaft','gasSource','turbine','exhaust']);
  for(const n of project.nodes){if(!allowed.has(n.type))throw Error('Unbekannter Bauteiltyp.');if(['pump','turbine'].includes(n.type)&&!shafts.some(v=>v.id===n.params.shaftId))throw Error('Antriebsmaschine benötigt gültige Welle.');if(n.type==='shaft'&&!project.nodes.some(v=>['pump','turbine'].includes(v.type)&&v.params.shaftId===n.id))throw Error('Nicht verwendete Welle.');}
  // Gas and shaft connections must not bypass the explicitly modelled chain.
  for(const e of project.edges)if(e.pipe&&!['fuel','ox'].includes(project.nodes.find(n=>n.id===e.from).medium))throw Error('Feedline-Druckverluste werden derzeit nur für flüssigen Brennstoff und Oxidator berechnet.');
  for(const n of [...Object.values(singles),...aux,...shafts]){
   if(n.medium!==(n.type==='shaft'?'mechanical':'gas'))throw Error('Falsches Medium an Gas- oder Wellenbauteil.');
   const inc=project.edges.filter(e=>e.to===n.id).length,out=project.edges.filter(e=>e.from===n.id).length;
   const expectedIn=n.type==='injector'?2:['gasSource','shaft'].includes(n.type)?0:1,expectedOut=['nozzle','exhaust','shaft'].includes(n.type)?0:1;
   if(inc!==expectedIn||out!==expectedOut)throw Error('Offene oder zusätzliche Gas-/Wellenanschlüsse.');
  }
  const graph={paths:{fuel:[],ox:[]},shafts,auxiliary};validateExtended(graph,project.design,errors);if(errors.length)return {ok:false,errors,warnings};
  warnings.push(...net.warnings,...base.warnings.filter(w=>['Idealer Vorentwurf:','CEA-Reaktanten:','2D-Glockenkontur:','Überexpandierte Düse:'].some(prefix=>w.startsWith(prefix))));
  warnings.push(`Stoffmodell: ${getPair(project.design).label}; ${channelNodes.length?'Kühlmittel gemäß T/p-Tabelle, sonst konstante Screeningwerte':'konstante Screeningwerte'}. Eintrittstemperaturen verändern die CEA-Thermochemie nicht.`);
  const auxiliaryStations=evaluateCycle(graph,project.design,base.performance.mdotKgS,cycle,warnings,errors);if(errors.length)return {ok:false,errors,warnings};
  const stations={...net.station,...auxiliaryStations};for(const type of ['injector','chamber','nozzle'])stations[singles[type].id]=base.stations[type];
  const edgeStates={...net.edgeState};for(const e of project.edges)if(!edgeStates[e.id]){const s=stations[e.from],t=cycle.turbines.find(v=>v.nodeId===e.from);edgeStates[e.id]={pressureBar:t?.outletPressureBar??s?.pressureBar,temperatureK:t?.outletTemperatureK??s?.temperatureK,massFlowKgS:s?.massFlowKgS,dropBar:0};}
  const totalMassFlowKgS=net.network.totalSourceMassFlowKgS+(auxiliary?.source.params.massFlowKgS??0),systemThrustN=project.design.thrustN+(cycle.auxiliary?.thrustN??0);
  if(cycle.auxiliary)Object.assign(cycle.auxiliary,{totalMassFlowKgS,systemIspS:systemThrustN/(totalMassFlowKgS*G0)});
  warnings.push('Verzweigtes Bedarfsnetz: Teilströme werden durch Injektor und Verbraucher vorgegeben. Druckabgleich je Zweig separat ausgewiesen; keine automatisch gelöste passive Stromaufteilung.');
  if(!net.network.balanced)warnings.push('Zusätzlicher Druckabgleich erforderlich: Die vorgegebenen Teilströme benötigen die ausgewiesenen Zweig-Drosselverluste.');
  if(net.consumers.length)warnings.push('Verbraucher sind Massenstrom-/Druckrandbedingungen. Preburner- und Filmeinträge erzeugen keine Verbrennungsleistung, Filmwirkung oder zusätzlichen Schub.');
  warnings.push('Kühlung: ausgewiesene Stoffdaten; feste CEA-Gasrandbedingung. Ungekühlte Bereiche, Filmwirksamkeit und Rückführschleifen werden nicht berechnet.');
  return {...base,errors:[],warnings,cycle,stations,edgeStates,feeds:net.feeds,network:{...net.network,totalMassFlowKgS,systemIspS:systemThrustN/(totalMassFlowKgS*G0)},meta:{...base.meta,feedModel:'Directed liquid demand trees, required pressure budgets and explicit balancing losses',coolantSource:channelNodes.length?coolingData?.coolant?.source:null,coolingSource:channelNodes.length?coolingData?.source:null,pressureBasis:channelNodes.length?'required total-pressure budgets; cooling static pressure march plus dynamic conversion':'required total-pressure budgets; constant-fluid static pressure screening',coolingModel:channelNodes.length?'Independent nonoverlapping co/counterflow segments with fixed hot-gas boundary':null}};
 }catch(e){return {ok:false,errors:[{nodeId:e.nodeId,message:e.message}],warnings};}
}
