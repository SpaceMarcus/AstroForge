import test from 'node:test';
import assert from 'node:assert/strict';
import { createProject, createTemplate, TEMPLATES, DEFAULT_PARAMS, parseProject, fingerprint, History, clone } from '../src/state.js';

function fluidPath(project, sourceId) {
  const path = [], seen = new Set();
  let id = sourceId;
  while (id) {
    assert.ok(!seen.has(id), `Unexpected loop at ${id}`);
    seen.add(id);
    const node = project.nodes.find(n => n.id === id);
    assert.ok(node, `Missing node ${id}`);
    path.push(node);
    if (node.type === 'injector' || node.type === 'exhaust') break;
    const next = project.edges.filter(edge => edge.from === id);
    assert.equal(next.length, 1, `Expected one continuation at ${id}, got ${next.length}`);
    id = next[0].to;
  }
  return path;
}

test('every cycle template roundtrips with its connections and mechanical references intact', () => {
  for (const template of TEMPLATES) {
    const original = createTemplate(template.id);
    const restored = parseProject(JSON.stringify(original));
    assert.equal(fingerprint(restored), fingerprint(original));
    assert.deepEqual(restored.nodes, original.nodes);
    assert.deepEqual(restored.edges, original.edges);
    for (const component of restored.nodes.filter(n => ['pump', 'turbine'].includes(n.type))) {
      assert.equal(restored.nodes.find(n => n.id === component.params.shaftId)?.type, 'shaft');
    }
    assert.equal(restored.edges.some(e => restored.nodes.find(n => n.id === e.from)?.type === 'shaft' || restored.nodes.find(n => n.id === e.to)?.type === 'shaft'), false);
  }
});

test('pump and regen template insertion replaces original edges without leaving bypass paths', () => {
  for (const id of ['electric', 'turbine']) {
    const project = createTemplate(id);
    const fuel = fluidPath(project, 'fuel-source');
    const ox = fluidPath(project, 'ox-source');
    assert.deepEqual(fuel.map(n => n.type), ['source', 'line', 'pump', 'valve', 'regen', 'injector']);
    assert.deepEqual(ox.map(n => n.type), ['source', 'line', 'pump', 'valve', 'injector']);
    assert.equal(project.edges.some(e => e.from === 'fuel-line' && e.to === 'fuel-valve'), false);
    assert.equal(project.edges.some(e => e.from === 'fuel-valve' && e.to === 'injector'), false);
    const gasSources = project.nodes.filter(n => n.type === 'gasSource');
    if (id === 'turbine') assert.deepEqual(fluidPath(project, gasSources[0].id).map(n => n.type), ['gasSource', 'turbine', 'exhaust']);
    else assert.equal(gasSources.length, 0);
  }
});

test('template editing cannot modify shared defaults, another template, or the legacy baseline', () => {
  const defaults = clone(DEFAULT_PARAMS);
  const changed = createTemplate('electric');
  changed.nodes.find(n => n.type === 'pump').params.riseBar = 99;
  changed.nodes.find(n => n.type === 'shaft').params.motorKW = 0;
  changed.nodes.find(n => n.type === 'regen').params.channelHeightMm = 9;
  const fresh = createTemplate('electric');
  assert.equal(fresh.nodes.find(n => n.type === 'pump').params.riseBar, defaults.pump.riseBar);
  assert.equal(fresh.nodes.find(n => n.type === 'shaft').params.motorKW, 30);
  assert.equal(fresh.nodes.find(n => n.type === 'regen').params.channelHeightMm, .75);
  assert.deepEqual(DEFAULT_PARAMS, defaults);
  const baseline = createProject();
  assert.equal(baseline.nodes.length, 9);
  assert.equal(baseline.nodes.some(n => ['pump', 'regen', 'shaft'].includes(n.type)), false);
  assert.equal(baseline.nodes.find(n => n.type === 'source').params.pressureBar, 55);
});

test('mechanical reassignment and available drive power invalidate calculations but drawing changes do not', () => {
  const project = createTemplate('turbine'), key = fingerprint(project);
  project.nodes.find(n => n.type === 'shaft').x += 100;
  assert.equal(fingerprint(project), key);
  const pump = project.nodes.find(n => n.type === 'pump');
  pump.params.shaftId = '';
  assert.notEqual(fingerprint(project), key);
  pump.params.shaftId = 'drive';
  assert.equal(fingerprint(project), key);
  project.nodes.find(n => n.type === 'shaft').params.motorKW = 10;
  assert.notEqual(fingerprint(project), key);
});

test('undo restores a deleted mechanical component and all of its parameter references', () => {
  const initial = createTemplate('electric'), history = new History(initial);
  const edited = clone(initial);
  edited.nodes = edited.nodes.filter(n => n.id !== 'drive');
  history.commit(edited);
  const restored = history.undo();
  assert.equal(fingerprint(restored), fingerprint(initial));
  assert.equal(restored.nodes.find(n => n.type === 'pump').params.shaftId, 'drive');
  assert.equal(restored.nodes.find(n => n.id === 'drive').type, 'shaft');
});

test('cycle import rejects nonnumeric parameter objects and unknown templates fail explicitly', () => {
  const project = createTemplate('electric');
  project.nodes.find(n => n.type === 'pump').params.shaftId = { id: 'drive' };
  assert.throws(() => parseProject(JSON.stringify(project)), /Komponentenparameter/);
  assert.throws(() => createTemplate('unknown'), /Unbekannte Vorlage/);
});
