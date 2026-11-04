import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createTemplate as newTemplate} from '../src/state.js';
const createTemplate=id=>{const p=newTemplate(id);for(const n of p.nodes)if(n.type==='regen')n.params={heatKW:50,dropBar:3,cpJkgK:2200};return p;};
import {solveProject} from '../src/physics.js';
const thermo=JSON.parse(readFileSync(new URL('../public/thermo.json',import.meta.url)));
const close=(a,b)=>assert.ok(Math.abs(a-b)<1e-8,`${a} != ${b}`);

test('electric template closes pump pressure work and reports shaft power and torque',()=>{
 const p=createTemplate('electric'),r=solveProject(p,thermo);assert.equal(r.ok,true,JSON.stringify(r.errors));
 assert.equal(r.cycle.pumps.length,2);assert.equal(r.cycle.shafts.length,1);
 for(const pump of r.cycle.pumps){
  const n=p.nodes.find(n=>n.id===pump.nodeId),rho=n.medium==='fuel'?810:1140;
  close(pump.hydraulicPowerKW,pump.massFlowKgS*n.params.riseBar*1e5/rho/1000);
  close(pump.shaftPowerKW,pump.hydraulicPowerKW/n.params.efficiency);
 }
 const shaft=r.cycle.shafts[0],omega=shaft.rpm*2*Math.PI/60;
 close(shaft.requiredPowerKW,r.cycle.pumps.reduce((s,p)=>s+p.shaftPowerKW,0));
 close(shaft.requiredTorqueNm,shaft.requiredPowerKW*1000/omega);
 close(shaft.availablePowerKW,shaft.motorKW);
});

test('lumped cooling preserves imposed energy and propagates outlet temperature',()=>{
 const p=createTemplate('electric'),r=solveProject(p,thermo),c=r.cycle.cooling[0];
 close(c.massFlowKgS*c.cpJkgK*(c.outletTemperatureK-c.inletTemperatureK),c.heatKW*1000);
 assert.ok(c.outletTemperatureK>c.inletTemperatureK);
 assert.ok(r.warnings.some(w=>w.includes('Wandtemperatur')));
});

test('separate auxiliary gas contributes turbine work, exhaust thrust and system propellant consumption',()=>{
 const p=createTemplate('turbine'),r=solveProject(p,thermo);assert.equal(r.ok,true,JSON.stringify(r.errors));
 const t=r.cycle.turbines[0],s=r.cycle.shafts[0],a=r.cycle.auxiliary;
 const g=p.nodes.find(n=>n.type==='gasSource'),tn=p.nodes.find(n=>n.type==='turbine');
 const power=g.params.massFlowKgS*g.params.cpJkgK*g.params.temperatureK*(1-(tn.params.outletBar/g.params.pressureBar)**((g.params.gamma-1)/g.params.gamma))*tn.params.efficiency/1000;
 close(t.powerKW,power);close(s.availablePowerKW,s.motorKW+s.turbinePowerKW*s.efficiency);
 close(a.totalMassFlowKgS,r.performance.mdotKgS+a.massFlowKgS);
 close(a.systemThrustN,r.performance.thrustN+a.thrustN);
 close(a.systemIspS,a.systemThrustN/(a.totalMassFlowKgS*9.80665));
 assert.ok(a.thrustN>0);assert.ok(a.exitTemperatureK>0);
});

test('power deficiency is reported without changing requested engine operating point',()=>{
 const p=createTemplate('electric');p.nodes.find(n=>n.type==='shaft').params.motorKW=0;
 const r=solveProject(p,thermo);assert.equal(r.ok,true);
 assert.equal(r.cycle.shafts[0].feasible,false);assert.ok(r.cycle.shafts[0].balanceKW<0);
 close(r.performance.thrustN,p.design.thrustN);
});

test('invalid mechanical reference, auxiliary circuit, bounds and excessive heat reject the result',()=>{
 const changes=[
  p=>p.nodes.find(n=>n.type==='pump').params.shaftId='missing',
  p=>p.nodes.find(n=>n.type==='pump').params.efficiency=0,
  p=>p.nodes.find(n=>n.type==='shaft').params.rpm=NaN,
  p=>p.nodes.find(n=>n.type==='regen').params.heatKW=5000,
  p=>p.nodes.find(n=>n.type==='turbine').params.outletBar=40,
  p=>p.edges=p.edges.filter(e=>e.to!==p.nodes.find(n=>n.type==='exhaust').id),
  p=>p.nodes.find(n=>n.type==='regen').medium='ox',
  p=>p.nodes.find(n=>n.type==='exhaust').params.exitBar=0,
 ];
 for(const change of changes){const p=createTemplate('turbine');change(p);assert.equal(solveProject(p,thermo).ok,false);}
});

test('an excessive fixed pump rise cannot produce a valid negative inlet pressure',()=>{
 const p=createTemplate('electric');p.nodes.find(n=>n.type==='pump').params.riseBar=150;
 const r=solveProject(p,thermo);assert.equal(r.ok,false);
 assert.ok(r.errors.some(e=>e.message.includes('Druckbudget')));
});

test('two independent shafts allocate each pump demand once',()=>{
 const p=createTemplate('electric'),drive=p.nodes.find(n=>n.type==='shaft');
 const other=structuredClone(drive);other.id='second-shaft';other.params.motorKW=20;p.nodes.push(other);
 p.nodes.find(n=>n.type==='pump'&&n.medium==='ox').params.shaftId=other.id;
 const r=solveProject(p,thermo);assert.equal(r.ok,true);
 assert.equal(r.cycle.shafts.length,2);
 close(r.cycle.shafts.reduce((a,s)=>a+s.requiredPowerKW,0),r.cycle.pumps.reduce((a,p)=>a+p.shaftPowerKW,0));
});

test('auxiliary nozzle pressure thrust is included separately from momentum thrust',()=>{
 const p=createTemplate('turbine');p.nodes.find(n=>n.type==='exhaust').params.exitBar=1.5;
 const r=solveProject(p,thermo);assert.equal(r.ok,true);const a=r.cycle.auxiliary;
 close(a.thrustN,a.massFlowKgS*a.exitVelocityMS+(a.exitPressureBar-p.design.paBar)*1e5*a.exitAreaM2);
 assert.ok(a.thrustN>a.massFlowKgS*a.exitVelocityMS);
});

test('zero cooling heat does not change fluid temperature; no phase/thermal closure is implied',()=>{
 const p=createTemplate('electric');p.nodes.find(n=>n.type==='regen').params.heatKW=0;
 const r=solveProject(p,thermo);assert.equal(r.ok,true);
 close(r.cycle.cooling[0].inletTemperatureK,r.cycle.cooling[0].outletTemperatureK);
 assert.ok(r.warnings.some(w=>w.includes('ohne Energieabschluss')));
});

test('fluid edges on a shaft and orphan mechanical shafts are invalid',()=>{
 const p=createTemplate('electric');p.edges.push({id:'mechanical-as-fluid',from:'drive',to:'fuel-pump'});
 assert.equal(solveProject(p,thermo).ok,false);
 const q=createTemplate('electric'),orphan=structuredClone(q.nodes.find(n=>n.type==='shaft'));orphan.id='orphan';q.nodes.push(orphan);
 assert.equal(solveProject(q,thermo).ok,false);
});
