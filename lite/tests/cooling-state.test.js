import test from 'node:test';
import assert from 'node:assert/strict';
import {createTemplate, parseProject, fingerprint, clone, History, DEFAULT_PARAMS} from '../src/state.js';
import {CHANNEL_DEFAULTS, CHANNEL_FIELDS} from '../src/cooling-config.js';

function legacyProject() {
  const project=createTemplate('electric');
  project.nodes.find(n=>n.type==='regen').params={heatKW:37,dropBar:2.5,cpJkgK:2300};
  return project;
}

test('old version-one cooling blocks remain lumped on import without silent migration',()=>{
  const old=legacyProject(),before=fingerprint(old);
  const parsed=parseProject(JSON.stringify(old));
  assert.deepEqual(parsed.nodes.find(n=>n.type==='regen').params,{heatKW:37,dropBar:2.5,cpJkgK:2300});
  assert.equal(fingerprint(parsed),before);
  assert.ok(!Object.hasOwn(parsed.nodes.find(n=>n.type==='regen').params,'mode'));
});

test('explicit cooling model upgrade is one reversible history change',()=>{
  const old=legacyProject(),before=fingerprint(old),history=new History(old);
  const upgraded=clone(old);
  upgraded.nodes.find(n=>n.type==='regen').params=clone(CHANNEL_DEFAULTS);
  history.commit(upgraded);
  assert.notEqual(fingerprint(history.current),before);
  assert.equal(history.current.nodes.find(n=>n.type==='regen').params.mode,'channels');
  const undo=history.undo();
  assert.equal(fingerprint(undo),before);
  assert.deepEqual(undo.nodes.find(n=>n.type==='regen').params,{heatKW:37,dropBar:2.5,cpJkgK:2300});
  const redo=history.redo();
  assert.deepEqual(redo.nodes.find(n=>n.type==='regen').params,CHANNEL_DEFAULTS);
  assert.ok(!Object.hasOwn(redo.nodes.find(n=>n.type==='regen').params,'heatKW'));
});

test('fresh templates have independent channel settings and preserve them through project roundtrip',()=>{
  const a=createTemplate('electric'),b=createTemplate('turbine');
  const aParams=a.nodes.find(n=>n.type==='regen').params,bParams=b.nodes.find(n=>n.type==='regen').params;
  assert.deepEqual(aParams,{...CHANNEL_DEFAULTS,channelHeightMm:.75});
  assert.deepEqual(bParams,{...CHANNEL_DEFAULTS,channelHeightMm:.75});
  assert.notEqual(aParams,bParams);
  aParams.channelHeightMm=3.4;
  assert.equal(bParams.channelHeightMm,.75);
  assert.equal(DEFAULT_PARAMS.regen.channelHeightMm,CHANNEL_DEFAULTS.channelHeightMm);
  const parsed=parseProject(JSON.stringify(a));
  assert.equal(parsed.nodes.find(n=>n.type==='regen').params.channelHeightMm,3.4);
  assert.equal(fingerprint(parsed),fingerprint(a));
});

test('each thermal model parameter invalidates the computation fingerprint',()=>{
  const base=createTemplate('electric'),before=fingerprint(base);
  for(const field of CHANNEL_FIELDS){
    const altered=clone(base),params=altered.nodes.find(n=>n.type==='regen').params;
    params[field.key]+=field.step;
    assert.notEqual(fingerprint(altered),before,field.key);
  }
  const layoutOnly=clone(base);
  const n=layoutOnly.nodes.find(n=>n.type==='regen');n.x+=90;n.y-=20;n.label='Neue Anzeige';
  assert.equal(fingerprint(layoutOnly),before,'layout and label must not invalidate physical calculation');
});
