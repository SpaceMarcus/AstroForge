import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {solveProject} from '../src/physics.js';

const data = JSON.parse(readFileSync(new URL('../public/thermo.json', import.meta.url)));
function project() {
 const nodes = [
  {id:'f',type:'source',medium:'fuel',params:{pressureBar:50,temperatureK:293.15}},
  {id:'fl',type:'line',medium:'fuel',section:'fuel',params:{lengthM:1,diameterMm:25,roughnessMm:0.01,k:0}},
  {id:'fv',type:'valve',medium:'fuel',section:'fuel',params:{k:2,open:true}},
  {id:'o',type:'source',medium:'ox',params:{pressureBar:50,temperatureK:90}},
  {id:'ol',type:'line',medium:'ox',section:'ox',params:{lengthM:1,diameterMm:25,roughnessMm:0.01,k:0}},
  {id:'ov',type:'valve',medium:'ox',section:'ox',params:{k:2,open:true}},
  {id:'i',type:'injector',medium:'gas',params:{fuelDropBar:6,oxDropBar:6}},
  {id:'c',type:'chamber',medium:'gas',params:{}}, {id:'n',type:'nozzle',medium:'gas',params:{}}
 ];
 return {format:'astroforge-lite',version:1,name:'Reference',design:{thrustN:10000,pcBar:30,of:2.6,eps:10,paBar:0,lstarM:1,contractionRatio:3},nodes,edges:[['f','fl'],['fl','fv'],['fv','i'],['o','ol'],['ol','ov'],['ov','i'],['i','c'],['c','n']].map(([from,to],i)=>({id:`e${i}`,from,to}))};
}
const close = (a,b,tol=1e-8)=>assert.ok(Math.abs(a-b)<tol,`${a} != ${b}`);
test('real CEA grid knot reproduces stored backend reference and mass closure',()=>{
 const r=solveProject(project(),data); assert.equal(r.ok,true,JSON.stringify(r.errors));
 close(r.performance.cstarMS,1778.022104213313,1e-6);
 close(r.performance.cf,1.7906496087124022,1e-8);
 close(r.performance.fuelKgS+r.performance.oxKgS,r.performance.mdotKgS);
 close(r.performance.oxKgS/r.performance.fuelKgS,2.6);
 close(r.performance.thrustN, r.performance.cf*30e5*Math.PI*r.geometry.throatRadiusM**2);
 assert.ok(r.geometry.contour.every(p=>Number.isFinite(p.x)&&p.r>0));
});
test('ambient pressure reduces ideal Cf and increases required mass at fixed target thrust',()=>{
 const p=project(),vac=solveProject(p,data);p.design.paBar=0.3; const amb=solveProject(p,data);
 assert.equal(amb.ok,true); close(amb.performance.cf,vac.performance.cf-0.3/30*10);
 assert.ok(amb.performance.mdotKgS>vac.performance.mdotKgS);
});
test('a longer feed line requires more pressure, underpressure is infeasible not a new operating point',()=>{
 const p=project(),a=solveProject(p,data); p.nodes[1].params.lengthM=3; p.nodes[0].params.pressureBar=20;
 const b=solveProject(p,data);assert.equal(b.ok,true); assert.ok(b.feeds.fuel.requiredBar>a.feeds.fuel.requiredBar);
 assert.ok(b.feeds.fuel.marginBar<0); close(a.performance.thrustN,b.performance.thrustN);
});
test('sections and ideal sensors do not change physical results',()=>{
 const p=project(),a=solveProject(p,data);p.nodes.forEach(n=>n.section=null);
 p.nodes.push({id:'s',type:'sensor',medium:'fuel',params:{quantity:'pressure'}});
 p.edges.find(e=>e.from==='fv').to='s';p.edges.push({id:'extra',from:'s',to:'i'});
 const b=solveProject(p,data);assert.equal(b.ok,true);close(a.feeds.fuel.requiredBar,b.feeds.fuel.requiredBar);
 close(a.performance.ispS,b.performance.ispS);
});
test('rejects disconnected, branched, cyclic, wrong-medium and incomplete graphs',()=>{
 const edits=[p=>p.nodes.push({id:'extra',type:'line',medium:'fuel',params:{}}),p=>p.edges.push({id:'branch',from:'f',to:'fv'}),p=>p.edges.push({id:'loop',from:'fv',to:'fl'}),p=>p.nodes[1].medium='ox',p=>p.edges.pop()];
 for(const edit of edits){const p=project();edit(p);assert.equal(solveProject(p,data).ok,false);}
});
test('rejects closed valves, nonfinite values, unsupported temperatures and out-of-grid chemistry',()=>{
 for(const edit of [p=>p.nodes[2].params.open=false,p=>p.design.thrustN=Infinity,p=>p.nodes[0].params.temperatureK=500,p=>p.design.pcBar=81,p=>p.nodes[1].params.diameterMm=0]){
  const p=project();edit(p);assert.equal(solveProject(p,data).ok,false);
 }
});
test('interior interpolation is bounded by neighboring knots and does not extrapolate',()=>{
 const p=project();p.design.pcBar=35;p.design.of=2.7;p.design.eps=12.5;
 const r=solveProject(p,data);assert.equal(r.ok,true); assert.ok(r.performance.cstarMS>1700 && r.performance.cstarMS<1900);
 p.design.of=1.99;assert.equal(solveProject(p,data).ok,false);
});
test('interior grid interpolation agrees with an independently evaluated CEA midpoint',()=>{
 const p=project();p.design.pcBar=35;p.design.of=2.7;p.design.eps=12.5;
 const r=solveProject(p,data);
 // Direct RocketCEABackend.calculate, not a table knot, on 2026-11-04.
 for(const [actual,reference] of [[r.performance.cstarMS,1772.8302615751027],[r.performance.cf,1.8273422816345906],[r.performance.tcK,3590.15110304542]]){
  assert.ok(Math.abs(actual/reference-1)<0.005,`interpolation error ${actual/reference-1}`);
 }
});
test('laminar fuel pressure drop agrees with independent Hagen–Poiseuille equation',()=>{
 const p=project();p.design.thrustN=100;p.nodes[2].params.k=0;p.nodes[6].params.fuelDropBar=0;
 const r=solveProject(p,data);assert.equal(r.ok,true);
 const volumeFlow=r.performance.fuelKgS/810;
 const expectedPa=128*1.8e-3*1*volumeFlow/(Math.PI*0.025**4);
 close((r.feeds.fuel.requiredBar-30)*1e5,expectedPa,1e-8);
});
test('malformed import structures produce errors instead of throwing',()=>{
 for(const p of [null,{}, {...project(),nodes:null},{...project(),nodes:[null]},{...project(),edges:[{}]}]){
  assert.doesNotThrow(()=>solveProject(p,data));assert.equal(solveProject(p,data).ok,false);
 }
});
test('visual contour has rounded joins and preserves throat and exit radii',()=>{
 const r=solveProject(project(),data),g=r.geometry;
 const throat=g.contour.findIndex(p=>p.r===g.throatRadiusM);
 assert.ok(throat>0);
 const left=g.contour[throat-1],center=g.contour[throat],right=g.contour[throat+1];
 assert.ok(Math.abs((center.r-left.r)/(center.x-left.x))<0.15,'convergent should approach a rounded throat');
 assert.ok(Math.abs((right.r-center.r)/(right.x-center.x))<0.15,'bell should leave a rounded throat');
 close(g.contour.at(-1).r,g.exitRadiusM);
 for(let i=1;i<g.contour.length;i++)assert.ok(g.contour[i].x>g.contour[i-1].x);
});
test('fixed CEA reactant states are explicit and not silently coupled to feed temperatures',()=>{
 const p=project(),a=solveProject(p,data);p.nodes[0].params.temperatureK=300;
 const b=solveProject(p,data);assert.deepEqual(a.performance,b.performance);
 assert.equal(b.meta.reactants.fuel.temperatureK,298.15);
 assert.equal(b.meta.reactants.oxidizer.temperatureK,90.18);
 assert.ok(b.warnings.some(w=>w.includes('nicht an die CEA')));
});
test('relative roughness outside the allowed hydraulic screening range is rejected',()=>{
 const p=project();p.nodes[1].params.diameterMm=10;p.nodes[1].params.roughnessMm=.51;
 const r=solveProject(p,data);assert.equal(r.ok,false);
 assert.ok(r.errors.some(e=>e.nodeId==='fl'&&e.message.includes('Rauheit')));
});
test('exit pressure matches direct CEA at the formerly worst midpoint',()=>{
 const p=project();p.design.pcBar=55;p.design.of=2.1;p.design.eps=8;
 const r=solveProject(p,data);assert.equal(r.ok,true);
 assert.ok(Math.abs(r.stations.n.pressureBar/0.9152583967941844-1)<.005);
});
test('injector has separate inlet losses rather than a misleading zero combined loss',()=>{
 const p=project();p.nodes[6].params.fuelDropBar=4;p.nodes[6].params.oxDropBar=7;
 const r=solveProject(p,data);assert.equal(r.ok,true);
 assert.equal(r.stations.i.dropBar,null);
 assert.equal(r.stations.i.fuelDropBar,4);assert.equal(r.stations.i.oxDropBar,7);
});
