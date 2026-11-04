import test from 'node:test';
import assert from 'node:assert/strict';
import {readJournal,saveSnapshot,documentChanges,componentReview} from '../src/project-journal.js';
const doc=()=>({name:'Demo',design:{choice:'A'},nodes:[{id:'n1',label:'Item',params:{value:1}}],edges:[]});
test('snapshots isolate documents, survive serialization and preserve list on storage failure',()=>{
 let raw=null;const storage={getItem:()=>raw,setItem:(_,v)=>raw=v};
 const project=doc(),list=saveSnapshot(storage,[],project,'First','s1');project.nodes[0].label='Changed';
 assert.equal(list[0].project.nodes[0].label,'Item');
 assert.deepEqual(readJournal(storage,JSON.parse),list);
 assert.throws(()=>saveSnapshot({setItem(){throw Error('full');}},list,project,'Next','s2'),/full/);
 assert.equal(list.length,1);
});
test('document diff reports additions, removals and changed properties without timestamps',()=>{
 const a=doc(),b=doc();b.updatedAt='later';assert.deepEqual(documentChanges(a,b),[]);
 b.nodes[0].params.value=2;b.edges.push({id:'e1',from:'a',to:'b'});
 assert.equal(documentChanges(a,b).length,2);
 assert.equal(documentChanges(b,a)[1].after,'Entfernt');
});
test('review never equates presence of data with validation, and stale errors are not current',()=>{
 const p=doc(),r={stations:{n1:{}},errors:[{nodeId:'n1',message:'Example'}]};
 assert.equal(componentReview(p,null,false)[0].status,'Nicht bewertet');
 assert.equal(componentReview(p,r,false)[0].status,'Hinweis offen');
 assert.deepEqual(componentReview(p,r,true)[0].messages,[]);
 assert.equal(componentReview(p,{stations:{n1:{}}},false)[0].status,'Ergebnis vorhanden');
});
test('corrupt archives and exceeded capacity are rejected without overwrite',()=>{
 assert.throws(()=>readJournal({getItem:()=>'{broken'},JSON.parse));
 assert.throws(()=>readJournal({getItem:()=>'{}'},JSON.parse));
 assert.throws(()=>saveSnapshot({},Array(30).fill({}),doc(),'Next','s2'),/30/);
});
