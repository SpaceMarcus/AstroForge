import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createTemplate,compactFeedlines,parseProject,fingerprint} from '../src/state.js';
import {solveProject} from '../src/physics.js';
const data=JSON.parse(readFileSync(new URL('../public/thermo.json',import.meta.url))),cooling=JSON.parse(readFileSync(new URL('../public/cooling-data.json',import.meta.url)));
test('arrow feedlines replace separate lines without changing the pressure-fed balance',()=>{
 const legacy=createTemplate('pressure'),p=compactFeedlines(legacy),a=solveProject(legacy,data,cooling),b=solveProject(p,data,cooling);
 assert.equal(b.ok,true,JSON.stringify(b.errors));assert.ok(!p.nodes.some(n=>n.type==='line'));assert.equal(b.performance.mdotKgS,a.performance.mdotKgS);
 assert.ok(Math.abs(a.feeds.fuel.requiredBar-b.feeds.fuel.requiredBar)<1e-8);
 assert.deepEqual(parseProject(JSON.stringify(p)).edges,p.edges);
 const before=fingerprint(p);p.edges.find(e=>e.pipe).pipe.lengthM+=1;assert.notEqual(fingerprint(p),before);
});
test('feedline length changes the hydraulic solution and errors identify the arrow',()=>{
 const p=compactFeedlines(createTemplate('pressure')),e=p.edges.find(e=>e.pipe),a=solveProject(p,data,cooling);e.pipe.lengthM+=10;const b=solveProject(p,data,cooling);
 assert.ok(b.edgeStates[e.id].dropBar>a.edgeStates[e.id].dropBar);e.pipe.diameterMm=0;
 const c=solveProject(p,data,cooling);assert.equal(c.ok,false);assert.ok(c.errors.some(v=>v.edgeId===e.id));
});
test('compact cooled template remains coupled and closes its energy balance',()=>{
 const r=solveProject(compactFeedlines(createTemplate('electric')),data,cooling);assert.equal(r.ok,true,JSON.stringify(r.errors));assert.ok(Math.abs(r.cycle.cooling[0].energyResidualW)<.01);
});

test('ideal gas arrows show turbine exit and chamber inlet rather than nozzle exhaust states',()=>{
 const p=createTemplate('turbine'),r=solveProject(p,data,cooling);assert.equal(r.ok,true);
 assert.equal(r.edgeStates['turbine-to-exhaust'].temperatureK,r.cycle.turbines[0].outletTemperatureK);
 assert.equal(r.edgeStates['turbine-to-exhaust'].pressureBar,r.cycle.turbines[0].outletPressureBar);
 const e=p.edges.find(e=>e.from==='chamber');assert.equal(r.edgeStates[e.id].pressureBar,p.design.pcBar);
 const f=p.edges.find(e=>e.from==='regen');assert.equal(r.edgeStates[f.id].temperatureK,r.cycle.cooling[0].outletTemperatureK);
 assert.equal(r.edgeStates[f.id].pressureBar,p.design.pcBar+p.nodes.find(n=>n.type==='injector').params.fuelDropBar);
});

test('migration preserves a custom hydraulic bore at downstream valves and is idempotent',()=>{
 const p=createTemplate('pressure');p.nodes.find(n=>n.id==='fuel-line').params.diameterMm=32;
 const q=compactFeedlines(p),a=solveProject(p,data,cooling),b=solveProject(q,data,cooling);
 assert.equal(b.ok,true);assert.ok(Math.abs(a.feeds.fuel.requiredBar-b.feeds.fuel.requiredBar)<1e-8);assert.deepEqual(compactFeedlines(q),q);
});
