import test from 'node:test';
import assert from 'node:assert/strict';
import {createProject,createTemplate,parseProject,fingerprint,History} from '../src/state.js';
import {PROPELLANT_PAIRS,getPair,getFluid,changePropellantPair} from '../src/propellants.js';
test('legacy files stay LOX/RP-1; every listed pair persists without changing geometry',()=>{
 assert.equal(getPair(parseProject(JSON.stringify(createProject())).design).id,'lox-rp1');
 for(const pair of PROPELLANT_PAIRS){const p=createTemplate('cooling-external'),geometry=p.design.lstarM;changePropellantPair(p,pair.id);
  const saved=parseProject(JSON.stringify(p));assert.equal(getPair(saved.design).id,pair.id);assert.equal(saved.design.of,pair.defaultOf);assert.equal(saved.design.lstarM,geometry);
  for(const n of saved.nodes.filter(n=>['source','coolantSource'].includes(n.type)))assert.equal(n.params.temperatureK,getFluid(pair[n.medium]).temperatureK);
 }
});
test('pair change is undoable, invalidates results and preserves custom names',()=>{
 const p=createProject();p.nodes[0].label='Mein Tank';const old=fingerprint(p),h=new History(p),next=structuredClone(p);changePropellantPair(next,'htp90-propane');h.commit(next);
 assert.notEqual(fingerprint(next),old);assert.equal(fingerprint(h.undo()),old);assert.equal(next.nodes[0].label,'Mein Tank');
});
test('unknown propellant pair is rejected on import instead of defaulting',()=>{
 const p=createProject();p.design.propellantPair='unknown';assert.throws(()=>parseProject(JSON.stringify(p)),/Unbekannte Treibstoff/);
});
