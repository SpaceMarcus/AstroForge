import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createTemplate,compactFeedlines} from '../src/state.js';
import {PROPELLANT_PAIRS,changePropellantPair} from '../src/propellants.js';
import {solveProject} from '../src/physics.js';
const legacy=JSON.parse(readFileSync(new URL('../public/thermo.json',import.meta.url)));
const catalog=JSON.parse(readFileSync(new URL('../public/propellant-data.json',import.meta.url)));
const data={...legacy,catalog},cooling=JSON.parse(readFileSync(new URL('../public/cooling-data.json',import.meta.url)));
function project(id){const p=compactFeedlines(createTemplate('pressure'));changePropellantPair(p,id);p.design.pcBar=50;for(const n of p.nodes)if(n.type==='source')n.params.pressureBar=100;return p;}
const solve=p=>solveProject(p,data,cooling);

test('every catalog combination solves with its own grid and fluid states',()=>{
 for(const pair of PROPELLANT_PAIRS){const p=project(pair.id),r=solve(p);assert.equal(r.ok,true,pair.id+': '+JSON.stringify(r.errors));assert.equal(r.meta.propellantPair,pair.id);assert.ok(r.meta.feedFluids.fuel.source);assert.ok(r.meta.feedFluids.ox.source);if(pair.id!=='lox-rp1')assert.deepEqual(r.meta.feedFluids,catalog.pairs[pair.id].fluids);assert.ok(Math.abs(r.performance.fuelKgS+r.performance.oxKgS-r.performance.mdotKgS)<1e-10);assert.ok(Math.abs(r.performance.oxKgS/r.performance.fuelKgS-pair.defaultOf)<1e-10);}
});
test('missing or mismatched pair data never silently falls back to RP-1',()=>{
 const p=project('lox-methane');assert.equal(solveProject(p,legacy,cooling).ok,false);
 const corrupted=structuredClone(data);corrupted.catalog.pairs['lox-methane'].pairId='lox-ethanol';assert.equal(solveProject(p,corrupted,cooling).ok,false);
 p.design.propellantPair='unknown';assert.equal(solve(p).ok,false);
});
test('a methane branching network preserves demand and uses methane hydraulic properties',()=>{
 const p=project('lox-methane'),e=p.edges.find(e=>e.from==='fuel-valve');e.from='branch';p.nodes.push({id:'branch',type:'branch',medium:'fuel',section:'cooling',label:'Branch',x:0,y:0,params:{diameterMm:18,k:0}},{id:'sink',type:'consumer',medium:'fuel',section:'cooling',label:'Sink',x:0,y:0,params:{massFlowKgS:.2,pressureBar:40,purpose:'other'}});p.edges.push({id:'branch-in',from:'fuel-valve',to:'branch'},{id:'branch-sink',from:'branch',to:'sink'});
 const r=solve(p);assert.equal(r.ok,true,JSON.stringify(r.errors));assert.ok(Math.abs(r.network.massResidualKgS)<1e-10);assert.equal(r.stations.sink.temperatureK,110);assert.equal(r.feeds['fuel-source'].massFlowKgS,r.performance.fuelKgS+.2);const rho=catalog.pairs['lox-methane'].fluids.fuel.rho,area=Math.PI*.018**2/4,velocity=(r.performance.fuelKgS+.2)/(rho*area);assert.ok(Math.abs(r.stations['fuel-valve'].dropBar-2*rho*velocity**2/2/1e5)<1e-10);
});
test('unsupported channel coolants and out-of-range fluid states are rejected',()=>{
 for(const id of ['lox-methane','lox-hydrogen','lox-propane']){const p=compactFeedlines(createTemplate('electric'));changePropellantPair(p,id);const r=solve(p);assert.equal(r.ok,false);assert.match(r.errors[0].message,/Kühlkanalmodell/);}
 const p=project('lox-methane');p.nodes.find(n=>n.id==='fuel-source').params.temperatureK=293.15;assert.equal(solve(p).ok,false);
 const q=project('n2o-ethanol');q.nodes.find(n=>n.id==='ox-source').params.pressureBar=2;assert.equal(solve(q).ok,false);
});

test('ethanol channels use each pair gas table and close the energy balance',()=>{
 const heats=[];
 for(const id of ['lox-ethanol','n2o-ethanol','htp90-ethanol']){
  const p=compactFeedlines(createTemplate('cooling-external'));changePropellantPair(p,id);p.design.pcBar=50;
  p.nodes.find(n=>n.id==='regen').params.coolingStart=.5;p.nodes.find(n=>n.id==='cool-outlet').params.massFlowKgS=4;
  // No legacy n-dodecane data supplied: the selected pair must provide its own table.
  const r=solveProject(p,data);assert.equal(r.ok,true,id+': '+JSON.stringify(r.errors));const c=r.cycle.cooling[0];
  assert.equal(r.meta.coolantSource,catalog.cooling[id].coolant.source);assert.equal(c.massFlowKgS,4);assert.ok(c.outletTemperatureK>293.15);assert.ok(Math.abs(c.energyResidualW)<.01);assert.ok(Math.abs(r.network.massResidualKgS)<1e-10);heats.push(c.heatKW);
 }
 assert.equal(new Set(heats.map(v=>v.toFixed(2))).size,3);
 const p=compactFeedlines(createTemplate('electric'));changePropellantPair(p,'lox-ethanol');const broken=structuredClone(data);delete broken.catalog.cooling['lox-ethanol'];assert.equal(solveProject(p,broken,cooling).ok,false);
});

test('unsupported cooling retains a clearly separate ideal engine analysis without a system success',()=>{
 for(const id of ['lox-methane','lox-hydrogen','lox-propane']){
  const p=compactFeedlines(createTemplate('electric'));changePropellantPair(p,id);const before=JSON.stringify(p),r=solve(p);
  assert.equal(r.ok,false);assert.equal(r.partial?.scope,'ideal-engine-only');assert.ok(r.partial.performance.ispS>0);assert.equal(r.partial.feeds,undefined);assert.equal(r.performance,undefined);assert.equal(JSON.stringify(p),before);
  const full=solve(project(id));assert.equal(r.partial.meta.propellantPair,id);assert.ok(r.partial.geometry.throatRadiusM>0);
 }
});
test('partial engine analysis never bypasses invalid engine inputs or missing pair data',()=>{
 const p=project('lox-methane');p.design.of=99;assert.equal(solve(p).partial,undefined);
 p.design.of=3.2;assert.equal(solveProject(p,legacy,cooling).partial,undefined);
 p.design.thrustN=-1;assert.equal(solve(p).partial,undefined);
});
test('valid ideal analysis matches full performance and geometry when the network is invalid',()=>{
 const p=project('htp90-propane'),full=solve(p);p.nodes.find(n=>n.type==='valve').params.open=false;
 const r=solve(p);assert.equal(r.ok,false);assert.deepEqual(r.partial.performance,full.performance);assert.deepEqual(r.partial.geometry,full.geometry);
});
