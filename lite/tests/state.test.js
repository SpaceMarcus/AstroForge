import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createProject,parseProject,fingerprint,History} from '../src/state.js';
test('portable project roundtrip and edits are independent',()=>{const p=createProject();const q=parseProject(JSON.stringify(p));assert.equal(fingerprint(p),fingerprint(q));q.design.pcBar=40;assert.equal(p.design.pcBar,30);});
test('layout is not physics; parameters and connectivity are',()=>{const p=createProject(),key=fingerprint(p);p.nodes[0].x=999;assert.equal(fingerprint(p),key);p.nodes[0].params.pressureBar=40;assert.notEqual(fingerprint(p),key);});
test('history preserves previous state and invalidates redo after new edit',()=>{const p=createProject(),h=new History(p);p.design.pcBar=40;h.commit(p);assert.equal(h.undo().design.pcBar,30);assert.equal(h.redo().design.pcBar,40);h.undo();p.design.pcBar=50;h.commit(p);assert.equal(h.future.length,0);});
test('imports reject duplicate ids, dangling edges and unsupported formats',()=>{for(const edit of [p=>p.version=9,p=>p.nodes[1].id=p.nodes[0].id,p=>p.edges[0].to='missing',p=>p.nodes[0].x=null,p=>p.design.pcBar=null]){const p=createProject();edit(p);assert.throws(()=>parseProject(JSON.stringify(p)));}});
test('reserved object property names cannot become component identifiers',()=>{for(const id of ['__proto__','constructor','prototype']){const p=createProject();p.nodes[0].id=id;assert.throws(()=>parseProject(JSON.stringify(p)),/Reservierte/);}});
test('section reassignment invalidates results because section compatibility is validated',()=>{const p=createProject(),key=fingerprint(p);p.nodes.find(n=>n.id==='fuel-line').section='ox';assert.notEqual(fingerprint(p),key);});
