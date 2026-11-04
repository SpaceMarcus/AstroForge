import test from 'node:test';
import assert from 'node:assert/strict';
import { nodeBounds, connectionPath } from '../src/graph.js';

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
