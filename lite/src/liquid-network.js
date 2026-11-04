import {coolingParams} from './cooling-layout.js';
import {coolantAt,staticPressureAt,solveCooling} from './cooling.js';

const LIQUID_TYPES=new Set(['source','coolantSource','line','valve','sensor','pump','regen','turn','manifold','branch','restriction','consumer']);
const ROOTS=new Set(['source','coolantSource']);
const K_TYPES=new Set(['turn','manifold','branch','restriction']);
const fail=(message,nodeId)=>{const e=new Error(message);e.nodeId=nodeId;throw e;};
function number(value,min,max,label,id){if(!Number.isFinite(value)||value<min||value>max)fail(`${label}: erwartet ${min}–${max}.`,id);return value;}

// A directed forest with prescribed terminal demand. Pressure imbalance is reported,
// never silently interpreted as a solved passive-network operating point.
export function solveLiquidNetwork(project,base,data){
 const nodes=project.nodes.filter(n=>LIQUID_TYPES.has(n.type)),map=new Map(nodes.map(n=>[n.id,n])),incoming=new Map(nodes.map(n=>[n.id,[]])),outgoing=new Map(nodes.map(n=>[n.id,[]]));
 const injector=project.nodes.find(n=>n.type==='injector'),injectorEdges=[];
 const edges=project.edges.filter(e=>map.has(e.from));
 const edgeIds=new Set(),pairs=new Set();
 for(const e of edges){
  const from=map.get(e.from),to=map.get(e.to);
  if(edgeIds.has(e.id)||pairs.has(e.from+'>'+e.to))fail('Doppelte Fluidverbindung.',e.from);edgeIds.add(e.id);pairs.add(e.from+'>'+e.to);
  if(e.to===injector.id)injectorEdges.push(e);else if(!to||to.medium!==from.medium)fail('Fluidverbindung: Medien oder Ziel passen nicht zusammen.',e.from);
  outgoing.get(e.from).push(e);if(to)incoming.get(e.to).push(e);
 }
 for(const medium of ['fuel','ox'])if(injectorEdges.filter(e=>map.get(e.from).medium===medium).length!==1)fail('Der Injektor benötigt genau einen Brennstoff- und einen Oxidatorzulauf.',injector.id);
 for(const n of nodes){
  if(!['fuel','ox'].includes(n.medium))fail('Flüssigkeitsbauteil benötigt Brennstoff oder Oxidator.',n.id);
  const inc=incoming.get(n.id).length,out=outgoing.get(n.id).length;
  if(inc!==(ROOTS.has(n.type)?0:1))fail('Ein Zulauf je Bauteil erforderlich; Zusammenführungen und Rückführkreise werden noch nicht gelöst.',n.id);
  if(n.type==='consumer'?out!==0:['branch','manifold'].includes(n.type)?out<1:out!==1)fail('Offener Anschluss oder Abzweigung ohne Branch/Manifold.',n.id);
  const p=n.params;
  if(ROOTS.has(n.type)){number(p.pressureBar,2,200,'Versorgungsdruck [bar]',n.id);number(p.temperatureK,n.medium==='ox'?85:288,n.medium==='ox'?95:303,'Eintrittstemperatur [K]',n.id);}
  if(n.type==='coolantSource'&&n.medium!=='fuel')fail('Separate Kühlversorgung unterstützt zunächst RP-1-Ersatzstoff.',n.id);
  if(n.type==='consumer'){number(p.massFlowKgS,.0001,100,'Verbraucher-Massenstrom [kg/s]',n.id);number(p.pressureBar,1,200,'Benötigter Eintrittsdruck [bar]',n.id);}
  if(K_TYPES.has(n.type)){number(p.diameterMm,1,200,'Bezugsdurchmesser [mm]',n.id);number(p.k,0,10000,'Verlustbeiwert K',n.id);}
  if(n.type==='restriction'){number(p.upstreamDiameterMm,p.diameterMm,200,'Zulaufdurchmesser [mm]',n.id);}
  if(n.type==='pump'){number(p.riseBar,.01,150,'Pumpendruckerhöhung',n.id);number(p.efficiency,.05,1,'Pumpenwirkungsgrad',n.id);if(!project.nodes.some(s=>s.type==='shaft'&&s.id===p.shaftId))fail('Pumpe benötigt eine gültige Welle.',n.id);}
  if(n.type==='valve'){number(p.k,0,10000,'Ventil-K',n.id);if(p.open!==true)fail('Geschlossenes Ventil bei vorgegebenem Bedarf.',n.id);}
  if(n.type==='regen'&&n.medium!=='fuel')fail('Kühlkanäle unterstützen zunächst RP-1-Ersatzstoff.',n.id);
  if(n.type==='sensor'&&!['pressure','temperature','massflow'].includes(p.quantity))fail('Unbekannte Messgröße.',n.id);
 }
 const roots=nodes.filter(n=>ROOTS.has(n.type)),order=[],visiting=new Set(),visited=new Set(),mass={},edgeMass={};
 function visit(n){
  if(visiting.has(n.id))fail('Fluidkreislauf: stationäre Rückführschleifen sind noch nicht unterstützt.',n.id);
  if(visited.has(n.id))return mass[n.id];visiting.add(n.id);
  let m=n.type==='consumer'?n.params.massFlowKgS:0;
  for(const e of outgoing.get(n.id)){const v=e.to===injector.id?(n.medium==='fuel'?base.performance.fuelKgS:base.performance.oxKgS):visit(map.get(e.to));edgeMass[e.id]=v;m+=v;}
  number(m,.0001,200,'Bauteil-Massenstrom',n.id);mass[n.id]=m;visiting.delete(n.id);visited.add(n.id);order.push(n);return m;
 }
 roots.forEach(visit);if(visited.size!==nodes.length)fail('Nicht versorgter Fluidkreis oder isolierte Bauteile.');order.reverse();
 const pressure=Object.fromEntries(nodes.map(n=>[n.id,200])),edgePressure=Object.fromEntries(edges.map(e=>[e.id,200]));
 let solved;
 for(let iteration=0;iteration<100;iteration++){
  const station={},edgeState={},drops={},cycles={pumps:[],cooling:[]},warnings=[],temperature={},bore={},rootFor={},typed={};
  for(const root of roots){
   const descendants=[];const walk=n=>{descendants.push(n);for(const e of outgoing.get(n.id))if(map.has(e.to))walk(map.get(e.to));};walk(root);
   const useTable=root.medium==='fuel'&&descendants.some(n=>n.type==='regen'&&n.params.mode==='channels');
   for(const n of descendants){rootFor[n.id]=root.id;typed[n.id]=useTable;}temperature[root.id]=root.params.temperatureK;bore[root.id]=root.medium==='ox'?22:18;
  }
  const fluid=(n,t,p,d,m)=>{
   if(typed[n.id]){const ps=staticPressureAt(data,t,p,Math.PI*(d/1000)**2/4,m),f=coolantAt(data,t,ps);return {rho:f.rhoKgM3,mu:f.muPaS};}
   return n.medium==='ox'?{rho:1140,mu:2e-4}:{rho:810,mu:1.8e-3};
  };
  const pipeLoss=(p,m,f,id)=>{
   number(p.lengthM,0,100,'Leitungslänge',id);number(p.diameterMm,1,200,'Leitungsdurchmesser',id);number(p.roughnessMm,0,Math.min(1,p.diameterMm/20),'Rauheit',id);number(p.k,0,10000,'Leitungs-K',id);
   const d=p.diameterMm/1000,A=Math.PI*d*d/4,v=m/(f.rho*A),re=f.rho*v*d/f.mu;
   if(v>100)fail('Flüssigkeitsgeschwindigkeit über 100 m/s.',id);
   const lam=64/re,turb=(-1.8*Math.log10((p.roughnessMm/1000/(3.7*d))**1.11+6.9/re))**-2,w=Math.max(0,Math.min(1,(re-2300)/1700)),darcy=lam+(turb-lam)*w;
   return {dropBar:(darcy*p.lengthM/d+p.k)*f.rho*v*v/2/1e5,velocityMS:v,reynolds:re,darcyFactor:darcy};
  };
  for(const n of order){
   const p=n.params,m=mass[n.id],tin=temperature[n.id],d=K_TYPES.has(n.type)||n.type==='line'?p.diameterMm:bore[n.id];
   number(d,1,200,'Bezugsdurchmesser [mm]',n.id);const f=fluid(n,tin,pressure[n.id],d,m);let drop=0,tout=tin,extra={};
   if(n.type==='line'){extra=pipeLoss(p,m,f,n.id);drop=extra.dropBar;}
   if(K_TYPES.has(n.type)||n.type==='valve'){const v=m/(f.rho*Math.PI*(d/1000)**2/4);if(v>100)fail('Flüssigkeitsgeschwindigkeit über 100 m/s.',n.id);drop=p.k*f.rho*v*v/2/1e5;extra={velocityMS:v};}
   if(n.type==='pump'){drop=-p.riseBar;const hydraulicPowerKW=m*p.riseBar*1e5/f.rho/1000;cycles.pumps.push({nodeId:n.id,shaftId:p.shaftId,pressureRiseBar:p.riseBar,hydraulicPowerKW,shaftPowerKW:hydraulicPowerKW/p.efficiency,massFlowKgS:m});}
   if(n.type==='regen'){
    if(p.mode==='channels'){const c=solveCooling({params:coolingParams(project,n),geometry:base.geometry,design:project.design,thermo:base.performance,data,massFlowKgS:m,inletTemperatureK:tin,inletPressureBar:pressure[n.id]});cycles.cooling.push({nodeId:n.id,...c});drop=c.dropBar;tout=c.outletTemperatureK;warnings.push(...c.warnings);}
    else {number(p.heatKW,0,5000,'Aufgeprägte Wärme',n.id);number(p.dropBar,0,100,'Kühldruckverlust',n.id);number(p.cpJkgK,100,10000,'Kühlmittel-cp',n.id);drop=p.dropBar;tout=tin+p.heatKW*1000/(m*p.cpJkgK);if(tout>650)fail('Kühlmittel außerhalb des Wärmebilanzmodells.',n.id);cycles.cooling.push({nodeId:n.id,heatKW:p.heatKW,dropBar:drop,inletTemperatureK:tin,outletTemperatureK:tout,massFlowKgS:m});}
   }
   station[n.id]={temperatureK:tin,outletTemperatureK:tout,massFlowKgS:m,dropBar:drop,...extra};drops[n.id]=drop;
   for(const e of outgoing.get(n.id)){
    const pipe=e.pipe||{lengthM:0,diameterMm:d,roughnessMm:0,k:0},ef=fluid(n,tout,edgePressure[e.id],pipe.diameterMm,edgeMass[e.id]);
    const loss=pipeLoss(pipe,edgeMass[e.id],ef,n.id);edgeState[e.id]={...loss,massFlowKgS:edgeMass[e.id],temperatureK:tout,medium:n.medium};
    if(map.has(e.to)){temperature[e.to]=tout;bore[e.to]=pipe.diameterMm;}
   }
  }
  let residual=0;const required={},balance=[];
  for(const n of [...order].reverse()){
   const targets=outgoing.get(n.id).map(e=>{const downstream=e.to===injector.id?project.design.pcBar+injector.params[n.medium==='fuel'?'fuelDropBar':'oxDropBar']:required[e.to];const req=downstream+edgeState[e.id].dropBar;edgeState[e.id].pressureBar=req;edgeState[e.id].outletPressureBar=downstream;return {e,req};});
   const outlet=n.type==='consumer'?n.params.pressureBar:Math.max(...targets.map(t=>t.req));
   required[n.id]=outlet+drops[n.id];number(required[n.id],.01,200,'Erforderlicher Gesamtdruck [bar]',n.id);station[n.id].pressureBar=required[n.id];
   for(const {e,req} of targets){const balancingDropBar=outlet-req;edgeState[e.id].balancingDropBar=balancingDropBar;edgeState[e.id].junctionPressureBar=outlet;
    if(targets.length>1)balance.push({nodeId:n.id,edgeId:e.id,massFlowKgS:edgeMass[e.id],requiredDropBar:balancingDropBar});
    residual=Math.max(residual,Math.abs(edgePressure[e.id]-req));edgePressure[e.id]=.5*(edgePressure[e.id]+req);
   }
   residual=Math.max(residual,Math.abs(pressure[n.id]-required[n.id]));pressure[n.id]=.5*(pressure[n.id]+required[n.id]);
  }
  if(residual<1e-5){solved={station,edgeState,cycles,warnings,balance,required};break;}
 }
 if(!solved)fail('Verzweigtes Kühlungs-Druckbudget konvergiert nicht.');
 const feeds={};for(const root of roots){const requiredBar=solved.required[root.id];feeds[root.id]={label:root.label,medium:root.medium,requiredBar,availableBar:root.params.pressureBar,marginBar:root.params.pressureBar-requiredBar,massFlowKgS:mass[root.id]};}
 const consumers=nodes.filter(n=>n.type==='consumer').map(n=>({nodeId:n.id,label:n.label,purpose:n.params.purpose||'other',massFlowKgS:mass[n.id],pressureBar:n.params.pressureBar,temperatureK:solved.station[n.id].temperatureK}));
 const totalSourceMassFlowKgS=roots.reduce((sum,n)=>sum+mass[n.id],0),consumerMassFlowKgS=consumers.reduce((sum,n)=>sum+n.massFlowKgS,0);
 const balanced=solved.balance.every(b=>b.requiredDropBar<.01);
 return {...solved,feeds,consumers,network:{mode:'prescribed-terminal-demand',balanced,balance:solved.balance,totalSourceMassFlowKgS,consumerMassFlowKgS,massResidualKgS:totalSourceMassFlowKgS-base.performance.mdotKgS-consumerMassFlowKgS}};
}
