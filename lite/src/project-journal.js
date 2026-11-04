// Local document versions. No calculation or physical compatibility checks.
export const JOURNAL_KEY='astroforge-lite-journal-v1';
export function readJournal(storage,parse){
 const raw=storage.getItem(JOURNAL_KEY);if(!raw)return [];
 const list=JSON.parse(raw);
 if(!Array.isArray(list)||list.length>30)throw Error('Entwurfsarchiv nicht lesbar.');
 return list.map(item=>{
  if(!item||typeof item.id!=='string'||!/^[\w-]+$/.test(item.id)||typeof item.name!=='string'||item.name.length>120||!Number.isFinite(Date.parse(item.createdAt)))throw Error('Ungültiger Entwurfsstand.');
  return {...item,project:parse(JSON.stringify(item.project))};
 });
}
export function saveSnapshot(storage,list,project,name,id){
 if(list.length>=30)throw Error('30 Entwurfsstände erreicht. Bitte zuerst das Archiv exportieren und einen Stand entfernen.');
 if(!name.trim()||name.trim().length>120)throw Error('Bitte einen Namen mit maximal 120 Zeichen eingeben.');
 const entry={id,name:name.trim(),createdAt:new Date().toISOString(),project:structuredClone(project)};
 const next=[entry,...list];
 storage.setItem(JOURNAL_KEY,JSON.stringify(next));
 return next;
}
export function documentChanges(before,after){
 const changes=[];
 const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
 if(before.name!==after.name)changes.push({kind:'Projekt',label:'Name',before:before.name,after:after.name});
 for(const key of new Set([...Object.keys(before.design),...Object.keys(after.design)]))if(!same(before.design[key],after.design[key]))changes.push({kind:'Entwurfsfeld',label:key,before:before.design[key],after:after.design[key]});
 for(const collection of ['nodes','edges']){
  const a=new Map(before[collection].map(x=>[x.id,x])),b=new Map(after[collection].map(x=>[x.id,x]));
  for(const id of new Set([...a.keys(),...b.keys()])){
   const old=a.get(id),next=b.get(id),label=next?.label||old?.label||id;
   if(!old||!next){changes.push({kind:collection==='nodes'?'Komponente':'Verbindung',label,before:old?'Vorhanden':'—',after:next?'Vorhanden':'Entfernt'});continue;}
   const keys=new Set([...Object.keys(old),...Object.keys(next)]);
   for(const key of keys)if(key!=='id'&&!same(old[key],next[key]))changes.push({kind:collection==='nodes'?'Komponente':'Verbindung',label:label+' · '+key,before:old[key],after:next[key]});
  }
 }
 return changes;
}
export function componentReview(project,result,isStale){
 return project.nodes.map(node=>{
  const errors=(result?.errors||[]).filter(e=>e.nodeId===node.id);
  const hasResult=!!result?.stations?.[node.id]||Object.values(result?.cycle||{}).some(values=>Array.isArray(values)&&values.some(v=>v?.nodeId===node.id));
  return {id:node.id,label:node.label,type:node.type,status:isStale?'Veraltet':errors.length?'Hinweis offen':hasResult?'Ergebnis vorhanden':'Nicht bewertet',messages:isStale?[]:errors.map(e=>e.message)};
 });
}
