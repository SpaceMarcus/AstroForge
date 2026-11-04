import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createProject, parseProject, fingerprint, History, clone } from '../src/state.js';
import { solveProject } from '../src/physics.js';

const thermo = JSON.parse(readFileSync(new URL('../public/thermo.json', import.meta.url)));

test('shipped default template computes a finite, supplied engine design', () => {
  const project = createProject();
  const result = solveProject(project, thermo);
  assert.equal(result.ok, true, JSON.stringify(result.errors));
  assert.equal(result.performance.thrustN, 10000);
  assert.ok(result.performance.ispS > 200 && result.performance.ispS < 400);
  assert.ok(result.feeds.fuel.marginBar > 0);
  assert.ok(result.feeds.ox.marginBar > 0);
  assert.equal(Object.keys(result.stations).length, project.nodes.length);
  for (const feed of Object.values(result.feeds)) {
    assert.ok(feed.requiredBar > project.design.pcBar);
    assert.ok(Number.isFinite(feed.requiredBar));
  }
  assert.ok(result.warnings.some(w => w.includes('Überexpandierte')),
    'The sea-level default must expose its ideal attached-flow approximation');
});

test('saved and imported default project preserves exact physics and identity', () => {
  const original = createProject();
  const imported = parseProject(JSON.stringify(original));
  assert.equal(fingerprint(original), fingerprint(imported));
  assert.deepEqual(solveProject(original, thermo), solveProject(imported, thermo));
  assert.deepEqual(imported.nodes.map(n => n.id), original.nodes.map(n => n.id));
});

test('layout and labels do not stale physics; parameter and connection edits do', () => {
  const project = createProject(), key = fingerprint(project);
  const moved = clone(project);
  moved.nodes[1].x += 150;
  moved.nodes[1].label = 'Updated display name';
  assert.equal(fingerprint(moved), key);
  assert.deepEqual(solveProject(moved, thermo).performance, solveProject(project, thermo).performance);
  moved.nodes[1].section = null;
  assert.equal(fingerprint(moved), key, 'Section placement is visual only');
  assert.deepEqual(solveProject(moved, thermo).performance, solveProject(project, thermo).performance);
  moved.nodes[1].params.lengthM += 2;
  assert.notEqual(fingerprint(moved), key);
  const disconnected = clone(project);
  disconnected.edges.pop();
  assert.notEqual(fingerprint(disconnected), key);
  assert.equal(solveProject(disconnected, thermo).ok, false);
});

test('history restores the complete valid graph after an invalid connection edit', () => {
  const initial = createProject(), history = new History(initial);
  const broken = clone(initial);
  broken.edges = broken.edges.filter(e => e.to !== 'injector');
  history.commit(broken);
  assert.equal(solveProject(history.current, thermo).ok, false);
  const restored = history.undo();
  assert.equal(fingerprint(restored), fingerprint(initial));
  assert.equal(solveProject(restored, thermo).ok, true);
  assert.equal(solveProject(history.redo(), thermo).ok, false);
});

test('sensor insertion through canonical project APIs keeps balances unchanged', () => {
  const initial = createProject(), modified = clone(initial);
  const edge = modified.edges.find(e => e.from === 'fuel-valve');
  const target = edge.to;
  edge.to = 'fuel-sensor';
  modified.nodes.push({id:'fuel-sensor', type:'sensor', label:'Fuel pressure', medium:'fuel', section:'fuel', x:600, y:350, params:{quantity:'pressure'}});
  modified.edges.push({id:'sensor-out',from:'fuel-sensor',to:target});
  const roundtrip = parseProject(JSON.stringify(modified));
  const before = solveProject(initial, thermo), after = solveProject(roundtrip, thermo);
  assert.equal(after.ok, true, JSON.stringify(after.errors));
  assert.deepEqual(after.performance, before.performance);
  assert.deepEqual(after.feeds, before.feeds);
  assert.ok(after.stations['fuel-sensor'].pressureBar > modified.design.pcBar);
});

test('malformed imports are rejected before reaching editor and worker', () => {
  const mutations = [
    p => p.version = 2,
    p => p.design.pcBar = null,
    p => p.nodes[0].id = '<script>',
    p => p.nodes[0].params = [],
    p => p.nodes[0].params.pressureBar = {value:50},
    p => p.nodes[1].id = p.nodes[0].id,
    p => p.edges[0].to = 'absent',
    p => p.edges[1].id = p.edges[0].id,
    p => p.nodes[0].section = 'arbitrary-section',
  ];
  for (const mutate of mutations) {
    const p = createProject(); mutate(p);
    assert.throws(() => parseProject(JSON.stringify(p)));
  }
  assert.throws(() => parseProject('not JSON'));
  assert.throws(() => parseProject(' '.repeat(2_000_001)));
});

test('well-formed but physically invalid imports produce solver errors', () => {
  for (const mutate of [
    p => p.design.pcBar = 100,
    p => p.nodes.find(n => n.id === 'fuel-source').params.temperatureK = 500,
    p => p.nodes.find(n => n.id === 'ox-valve').params.open = false,
    p => p.edges.push({id:'invalid-branch',from:'ox-source',to:'ox-valve'})
  ]) {
    const p = createProject(); mutate(p);
    const imported = parseProject(JSON.stringify(p));
    const result = solveProject(imported, thermo);
    assert.equal(result.ok, false);
    assert.ok(result.errors.length > 0);
  }
});
