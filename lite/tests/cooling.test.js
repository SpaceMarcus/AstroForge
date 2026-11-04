import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {coolantAt,gasAt,channelTransport,machFromArea,bartzHTC,solveCooling} from '../src/cooling.js';
import {solveProject} from '../src/physics.js';
import {createTemplate} from '../src/state.js';
const thermo=JSON.parse(readFileSync(new URL('../public/thermo.json',import.meta.url)));
const data=JSON.parse(readFileSync(new URL('../public/cooling-data.json',import.meta.url)));
const close=(a,b,t=1e-6)=>assert.ok(Math.abs(a-b)<=t,`${a} != ${b}`);
// Deliberately insulating wall: a computable but thermally infeasible design exercises reporting.
function fixture(){const p=createTemplate('electric');p.design.lstarM=.2;const n=p.nodes.find(n=>n.type==='regen');Object.assign(n.params,{wallThicknessMm:5,wallConductivityWmK:5});return p;}
const solve=p=>solveProject(p,thermo,data);
test('rectangular square duct laminar references and isentropic Mach are independent known values',()=>{
 const t=channelTransport(1000,7,.002,.002,0);close(t.darcy,.0569184,1e-8);close(t.nusselt,3.610224,1e-6);
 close(machFromArea(1,1.4,false),1);close(machFromArea(1.6875,1.4,true),2,1e-8);
 const m=machFromArea(2,1.4,false);close(m,.305903834,1e-8);
 assert.throws(()=>channelTransport(10000,7,.001,.001,.0001),/Rauheit/);
});
test('Bartz SI reference calculation and pressure scaling',()=>{
 const args={gas:{muPaS:1e-4,cpJkgK:2000,prandtl:.7,gamma:1.2},pcBar:30,cstarMS:1700,tcK:3400,throatRadiusM:.025,curvatureRatio:1.5,areaRatio:1,mach:1,wallTemperatureK:800};
 const sigma=(.5*800/3400*1.1+.5)**-.68*1.1**-.12;
 close(bartzHTC(args),.026*.15848931924611134*2000/.7**.6*(3e6/1700)**.8*.05**-.2*(4/3)**.1*sigma,1e-7);
 close(bartzHTC({...args,pcBar:60})/bartzHTC(args),2**.8,1e-10);
});
test('property tables interpolate real liquid data and reject extrapolation and invalid phase',()=>{
 const f=coolantAt(data,300,40);assert.ok(f.rhoKgM3>700&&f.rhoKgM3<800);assert.ok(f.hJkg<0);
 assert.throws(()=>coolantAt(data,700,40),/Stoffdatentabelle/);assert.throws(()=>coolantAt(data,300,201),/Stoffdatentabelle/);
 assert.throws(()=>coolantAt(data,630,1),/Phase/);assert.ok(gasAt(data,30,2.6).cpJkgK>1000);
});
test('channel model conserves total coolant energy, reports wall violation and propagates temperature',()=>{
 const p=fixture(),edge=p.edges.find(e=>e.from===p.nodes.find(n=>n.type==='regen').id);p.nodes.push({id:'hot-line',type:'line',medium:'fuel',section:'fuel',params:{lengthM:.1,diameterMm:15,roughnessMm:.005,k:0}});p.edges.push({id:'hot-out',from:'hot-line',to:edge.to});edge.to='hot-line';const r=solve(p);assert.equal(r.ok,true,JSON.stringify(r.errors));const c=r.cycle.cooling[0];
 assert.equal(c.mode,'channels');assert.equal(c.feasible,false);assert.ok(c.wallMarginK<0);assert.ok(Math.abs(c.energyResidualW)<.1);
 assert.ok(c.heatKW>0&&c.dropBar>0);assert.ok(c.outletTemperatureK>c.inletTemperatureK);
 const downstream=p.edges.find(e=>e.from===c.nodeId).to;close(r.stations[downstream].temperatureK,c.outletTemperatureK);
 close(c.inletPressureBar,r.stations[c.nodeId].pressureBar,1e-5);close(c.outletPressureBar,c.inletPressureBar-c.dropBar);
 assert.ok(c.stations[0].coolantTemperatureK>c.stations.at(-1).coolantTemperatureK);
 assert.ok(c.stations.every(s=>s.hotWallTemperatureK>s.coldWallTemperatureK&&s.coldWallTemperatureK>s.coolantTemperatureK));
});
test('mesh refinement converges heat and peak temperature without changing displayed geometry',()=>{
 const p=fixture();p.nodes.find(n=>n.type==='regen').params.stations=80;const a=solve(p);
 p.nodes.find(n=>n.type==='regen').params.stations=240;const b=solve(p);assert.equal(a.ok,true);assert.equal(b.ok,true);
 const x=a.cycle.cooling[0],y=b.cycle.cooling[0];assert.ok(Math.abs(x.heatKW/y.heatKW-1)<.005);assert.ok(Math.abs(x.maxHotWallTemperatureK-y.maxHotWallTemperatureK)<5);assert.deepEqual(a.geometry,b.geometry);
});
test('chamber geometry and channel height affect heating and hydraulic losses',()=>{
 const p=fixture(),a=solve(p).cycle.cooling[0];p.design.lstarM=.3;const b=solve(p).cycle.cooling[0];assert.ok(b.heatKW>a.heatKW);
 p.design.lstarM=.2;p.nodes.find(n=>n.type==='regen').params.channelHeightMm=3;const c=solve(p).cycle.cooling[0];assert.ok(c.dropBar<a.dropBar);assert.notEqual(c.maxHotWallTemperatureK,a.maxHotWallTemperatureK);
});
test('missing data, invalid channel bounds, unknown modes and excess temperature produce errors',()=>{
 const p=fixture();assert.equal(solveProject(p,thermo).ok,false);
 for(const change of [n=>n.params.stations=39,n=>n.params.channelCount=22.5,n=>n.params.mode='typo']){const q=fixture();change(q.nodes.find(n=>n.type==='regen'));assert.equal(solve(q).ok,false);}
 const q=createTemplate('electric');q.design.lstarM=1.2;q.design.of=2.6;assert.equal(solve(q).ok,false);assert.match(solve(q).errors[0].message,/Stoffdatentabelle/);
});
test('high-loss channels reconstruct needed supply pressure rather than failing at a low initial guess',()=>{
 const p=createTemplate('electric');p.design.lstarM=.2;p.design.of=2.6;p.nodes.find(n=>n.type==='regen').params.channelHeightMm=.4;
 const r=solve(p);assert.equal(r.ok,true,JSON.stringify(r.errors));const c=r.cycle.cooling[0];
 assert.ok(c.dropBar>30);assert.ok(r.feeds.fuel.marginBar<0);assert.ok(c.inletPressureBar>60);
 assert.ok(c.inletStaticPressureBar<c.inletPressureBar);assert.ok(c.outletStaticPressureBar<c.outletPressureBar);
 close(c.outletPressureBar,p.design.pcBar+p.nodes.find(n=>n.type==='injector').params.fuelDropBar,1e-5);
});
test('higher chamber pressure changes geometric thermal load; a second full cooling jacket is rejected',()=>{
 const p=fixture(),a=solve(p);p.design.pcBar=40;const b=solve(p);assert.equal(b.ok,true,JSON.stringify(b.errors));assert.notEqual(a.cycle.cooling[0].maxHeatFluxWm2,b.cycle.cooling[0].maxHeatFluxWm2);
 const n=p.nodes.find(n=>n.type==='regen'),edge=p.edges.find(e=>e.from===n.id);p.nodes.push({...structuredClone(n),id:'second-jacket'});p.edges.push({id:'second-out',from:'second-jacket',to:edge.to});edge.to='second-jacket';assert.equal(solve(p).ok,false);assert.ok(solve(p).errors.some(e=>e.message.includes('überlappen')));
});
test('new demo templates close thermal, supply and drive budgets while excessive pump rise stays invalid',()=>{
 for(const id of ['electric','turbine']){const p=createTemplate(id),r=solve(p);assert.equal(r.ok,true,JSON.stringify(r.errors));const c=r.cycle.cooling[0];assert.equal(c.feasible,true);assert.ok(c.wallMarginK>0&&c.wallMarginK<50);assert.ok(r.feeds.fuel.marginBar>0);assert.ok(r.cycle.shafts.every(s=>s.feasible));assert.ok(Math.abs(c.energyResidualW)<.01);assert.ok(c.outletTemperatureK<633);}
 const p=createTemplate('electric');p.nodes.find(n=>n.type==='pump'&&n.medium==='fuel').params.riseBar=150;const r=solve(p);assert.equal(r.ok,false);assert.ok(r.errors.some(e=>e.message.includes('Nicht positives Druckbudget')));
});
test('boundary temperatures participate in the reported maximum and heat is counted only once',()=>{
 const p=createTemplate('electric');p.nodes.find(n=>n.type==='regen').params.stations=40;const low=solve(p);p.nodes.find(n=>n.type==='regen').params.stations=400;const high=solve(p);
 for(const r of [low,high]){assert.equal(r.ok,true,JSON.stringify(r.errors));const c=r.cycle.cooling[0],points=c.stations;close(points[0].xM,0);close(points.at(-1).xM,r.geometry.contour.at(-1).x);assert.ok(points.some(s=>s.xM===c.throatX));close(Math.max(...points.map(s=>s.hotWallTemperatureK)),c.maxHotWallTemperatureK);close(points.reduce((sum,s)=>sum+s.segmentHeatW,0),c.heatKW*1000,1e-6);assert.ok(points.filter(s=>s.sampleKind==='boundary').every(s=>s.segmentHeatW===0));}
 assert.ok(Math.abs(low.cycle.cooling[0].maxHotWallTemperatureK-high.cycle.cooling[0].maxHotWallTemperatureK)<1);
});
test('flow direction follows the selected inlet; partial jackets conserve energy and bound their profiles',()=>{
 for(const direction of ['counter','co']){
  const p=fixture(),n=p.nodes.find(n=>n.type==='regen');Object.assign(n.params,{flowDirection:direction,coolingStart:.2,coolingEnd:.8});
  const r=solve(p);assert.equal(r.ok,true,JSON.stringify(r.errors));const c=r.cycle.cooling[0],end=r.geometry.contour.at(-1).x;
  close(c.stations[0].xM,.2*end);close(c.stations.at(-1).xM,.8*end);close(c.cooledLengthM,.6*end);
  const inlet=direction==='co'?c.stations[0]:c.stations.at(-1),outlet=direction==='co'?c.stations.at(-1):c.stations[0];
  close(inlet.coolantTemperatureK,c.inletTemperatureK);close(outlet.coolantTemperatureK,c.outletTemperatureK);
  assert.ok(c.outletTemperatureK>c.inletTemperatureK);assert.ok(c.dropBar>0);assert.ok(Math.abs(c.energyResidualW)<.01);
  assert.equal(c.fullCoverage,false);assert.ok(c.warnings.some(w=>w.includes('Ungekühlte Bereiche')));
 }
});
test('older channel projects retain full counterflow coverage and invalid ranges fail explicitly',()=>{
 const p=fixture(),n=p.nodes.find(n=>n.type==='regen');delete n.params.flowDirection;delete n.params.coolingStart;delete n.params.coolingEnd;
 const r=solve(p);assert.equal(r.ok,true);assert.equal(r.cycle.cooling[0].flowDirection,'counter');assert.equal(r.cycle.cooling[0].fullCoverage,true);
 for(const edit of [{coolingStart:.8,coolingEnd:.2},{coolingStart:-.1},{coolingEnd:1.1},{flowDirection:'wrong'}]){
  const q=structuredClone(p);Object.assign(q.nodes.find(n=>n.type==='regen').params,edit);assert.equal(solve(q).ok,false);
 }
});
test('turn and manifold use their explicit reference area and preserve the serial feed balance',()=>{
 const baseline=solve(createTemplate('pressure'));
 for(const type of ['turn','manifold']){
  const p=createTemplate('pressure'),edge=p.edges.find(e=>e.from==='fuel-valve');
  p.nodes.push({id:'fitting',type,label:type,medium:'fuel',section:'fuel',x:0,y:0,params:{diameterMm:18,k:2}});
  p.edges.push({id:'fitting-out',from:'fitting',to:edge.to});edge.to='fitting';
  const r=solve(p);assert.equal(r.ok,true,JSON.stringify(r.errors));const m=r.feeds.fuel.massFlowKgS,A=Math.PI*.018**2/4;
  close(r.stations.fitting.dropBar,2*m*m/(2*810*A*A)/1e5);
  close(r.feeds.fuel.requiredBar-baseline.feeds.fuel.requiredBar,r.stations.fitting.dropBar);
  p.nodes.at(-1).params.diameterMm=0;assert.equal(solve(p).ok,false);
 }
});
