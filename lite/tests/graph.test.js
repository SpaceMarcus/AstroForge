import test from 'node:test';
import assert from 'node:assert/strict';
import { nodeBounds, connectionPath, fluidPortsFor, mechanicalLinks } from '../src/graph.js';

test('graph bounds include negative and widely spaced positions', () => {
  assert.deepEqual(nodeBounds([{x:-100,y:20},{x:500,y:-200}]), {x:-100,y:-200,width:752,height:324});
});
test('empty graph has a usable viewport', () => {
  const bounds = nodeBounds([]);
  assert.ok(bounds.width > 0 && bounds.height > 0);
});
test('connection preserves both endpoints including reverse direction', () => {
  assert.match(connectionPath({x:300,y:40},{x:100,y:200}), /^M 300 40 C .* 100 200$/);
});

test('mechanical shaft has no fluid ports and cycle boundaries have only one', () => {
  assert.deepEqual(fluidPortsFor('shaft'), {input:false,output:false});
  for(const type of ['source','gasSource']) assert.deepEqual(fluidPortsFor(type), {input:false,output:true});
  for(const type of ['nozzle','exhaust']) assert.deepEqual(fluidPortsFor(type), {input:true,output:false});
  for(const type of ['pump','regen','turbine','line','valve']) assert.deepEqual(fluidPortsFor(type), {input:true,output:true});
});

test('shaft coupling is independent of fluid connections and ignores invalid shaft references', () => {
  const shaft={id:'shaft-1',type:'shaft',medium:'mechanical',params:{rpm:30000}};
  const pump={id:'pump-1',type:'pump',params:{shaftId:'shaft-1'}};
  const turbine={id:'turbine-1',type:'turbine',params:{shaftId:'shaft-1'}};
  const bad={id:'pump-2',type:'pump',params:{shaftId:'pump-1'}};
  const missing={id:'pump-3',type:'pump',params:{shaftId:'missing'}};
  const line={id:'line-1',type:'line',params:{shaftId:'shaft-1'}};
  assert.deepEqual(mechanicalLinks([shaft,pump,turbine,bad,missing,line]), [{component:pump,shaft},{component:turbine,shaft}]);
});
