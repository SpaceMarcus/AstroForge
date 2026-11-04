import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createTemplate,compactFeedlines} from '../src/state.js';
import {solveProject} from '../src/physics.js';
const data=JSON.parse(readFileSync(new URL('../public/thermo.json',import.meta.url))),cooling=JSON.parse(readFileSync(new URL('../public/cooling-data.json',import.meta.url)));
const solve=p=>solveProject(p,data,cooling);
function branched(){const p=compactFeedlines(createTemplate('electric')),edge=p.edges.find(e=>e.from==='regen');
 p.nodes.push({id:'split',type:'branch',label:'Split',medium:'fuel',section:'cooling',x:0,y:0,params:{diameterMm:18,k:0}});
 p.nodes.push({id:'pb',type:'consumer',label:'Preburner fuel',medium:'fuel',section:'cooling',x:0,y:0,params:{massFlowKgS:.2,pressureBar:25,purpose:'preburner'}});
 p.edges.push({id:'to-main',from:'split',to:edge.to},{id:'to-pb',from:'split',to:'pb'});edge.to='split';return p;
}
test('coolant can split after regen between injector and preburner demand',()=>{
 const p=branched(),r=solve(p);assert.equal(r.ok,true,JSON.stringify(r.errors));assert.ok(Math.abs(r.network.massResidualKgS)<1e-9);
 assert.ok(Math.abs(r.stations.regen.massFlowKgS-r.performance.fuelKgS-.2)<1e-9);
 assert.equal(r.edgeStates['to-pb'].massFlowKgS,.2);assert.equal(r.edgeStates['to-main'].massFlowKgS,r.performance.fuelKgS);
 assert.equal(r.network.balanced,false);assert.ok(r.edgeStates['to-pb'].balancingDropBar>10);assert.ok(Math.abs(r.cycle.cooling[0].energyResidualW)<.01);
});
test('restriction loss uses throat velocity and does not invent a flow split',()=>{
 const p=branched(),edge=p.edges.find(e=>e.id==='to-pb');p.nodes.push({id:'restriction',type:'restriction',label:'Restriction',medium:'fuel',section:'cooling',x:0,y:0,params:{diameterMm:10,upstreamDiameterMm:18,k:2}});edge.to='restriction';p.edges.push({id:'r-out',from:'restriction',to:'pb'});
 const r=solve(p);assert.equal(r.ok,true,JSON.stringify(r.errors));assert.ok(r.stations.restriction.dropBar>0);assert.equal(r.stations.restriction.massFlowKgS,.2);
 p.nodes.at(-1).params.upstreamDiameterMm=5;assert.equal(solve(p).ok,false);
});
test('separate coolant supply can discharge to its own consumer without changing main fuel demand',()=>{
 const p=branched();p.edges=p.edges.filter(e=>!['to-main','to-pb'].includes(e.id));p.nodes=p.nodes.filter(n=>n.id!=='split');const inlet=p.edges.find(e=>e.to==='regen');inlet.to='injector';p.edges.find(e=>e.from==='regen').to='pb';
 p.nodes.push({id:'cool-source',type:'coolantSource',medium:'fuel',label:'Separate coolant',section:'cooling',x:0,y:0,params:{pressureBar:60,temperatureK:293.15}});p.edges.push({id:'cool-in',from:'cool-source',to:'regen'});p.nodes.find(n=>n.id==='pb').params.massFlowKgS=2;
 const r=solve(p);assert.equal(r.ok,true,JSON.stringify(r.errors));assert.equal(r.stations.regen.massFlowKgS,2);assert.ok(Math.abs(r.network.massResidualKgS)<1e-9);assert.equal(r.feeds['cool-source'].massFlowKgS,2);
});
test('zero demand, loops and unmodelled merges are rejected',()=>{
 const p=branched();p.nodes.find(n=>n.id==='pb').params.massFlowKgS=0;assert.equal(solve(p).ok,false);
 const q=branched();q.edges.push({id:'loop',from:'pb',to:'regen'});assert.equal(solve(q).ok,false);
 const z=branched();z.edges.push({id:'merge',from:'split',to:'fuel-valve'});assert.equal(solve(z).ok,false);
});

test('separate-supply and branched workspace templates roundtrip and solve after line compaction',()=>{
 for(const id of ['cooling-network','cooling-external']){const r=solve(compactFeedlines(createTemplate(id)));assert.equal(r.ok,true,JSON.stringify(r.errors));assert.ok(Math.abs(r.network.massResidualKgS)<1e-9);}
});
test('two nonoverlapping jackets can run in opposite directions from one manifold',()=>{
 const p=compactFeedlines(createTemplate('cooling-external')),m=p.nodes.find(n=>n.id==='cool-manifold'),a=p.nodes.find(n=>n.id==='regen');m.params.axialPosition=.45;
 Object.assign(a.params,{coolingStart:0,coolingEnd:.45,flowDirection:'counter'});
 const b=structuredClone(a);b.id='regen-co';b.label='Co-current';Object.assign(b.params,{flowDirection:'co',coolingStart:.45,coolingEnd:1});p.nodes.push(b);
 const sink=structuredClone(p.nodes.find(n=>n.id==='cool-outlet'));sink.id='co-out';p.nodes.push(sink);p.edges.push({id:'manifold-co',from:m.id,to:b.id},{id:'co-exit',from:b.id,to:sink.id});
 const r=solve(p);assert.equal(r.ok,true,JSON.stringify(r.errors));assert.equal(r.cycle.cooling.length,2);assert.ok(r.cycle.cooling.some(c=>c.flowDirection==='co'));assert.ok(r.cycle.cooling.some(c=>c.flowDirection==='counter'));
 for(const c of r.cycle.cooling){assert.ok(Math.abs(c.energyResidualW)<.01);assert.ok(Math.abs(c.inletXM/r.geometry.contour.at(-1).x-.45)<1e-9);}
 assert.equal(r.feeds['cool-source'].massFlowKgS,4);
});


test('constant-property restriction matches independent K-loss calculation',()=>{
 const p=branched();p.nodes.find(n=>n.id==='regen').params={mode:'lumped',heatKW:0,dropBar:0,cpJkgK:2100};
 const e=p.edges.find(e=>e.id==='to-pb');e.to='narrow';p.nodes.push({id:'narrow',type:'restriction',medium:'fuel',params:{upstreamDiameterMm:18,diameterMm:10,k:2}});p.edges.push({id:'narrow-out',from:'narrow',to:'pb'});
 const r=solve(p);assert.equal(r.ok,true,JSON.stringify(r.errors));const area=Math.PI*.01**2/4,velocity=.2/(810*area),expected=2*810*velocity**2/2/1e5;
 assert.ok(Math.abs(r.stations.narrow.dropBar-expected)<1e-12);
});
test('branched networks reject unmodelled gas-line losses and incorrect shaft media',()=>{
 const p=branched();p.edges.find(e=>e.from==='chamber').pipe={lengthM:1,diameterMm:20,roughnessMm:0,k:0};assert.equal(solve(p).ok,false);
 const q=branched();q.nodes.find(n=>n.type==='shaft').medium='fuel';assert.equal(solve(q).ok,false);
});
