import {JOURNAL_KEY,readJournal,saveSnapshot,documentChanges,componentReview} from './project-journal.js';

export function setupReview({getProject,getResult,isStale,hasDrafts,parseProject,replaceProject,showDialog,download,toast,esc,onPresentation}){
 let snapshots=[],archiveError=false;
 try{snapshots=readJournal(localStorage,parseProject);}catch{archiveError=true;}
 const date=s=>new Date(s).toLocaleString('de-DE');
 const value=v=>v===undefined?'—':typeof v==='object'?JSON.stringify(v):String(v);
 const dialog=()=>document.querySelector('#dialog');
 const newId=()=>crypto.randomUUID();
 function persist(next){localStorage.setItem(JOURNAL_KEY,JSON.stringify(next));snapshots=next;}
 function guard(){if(archiveError)throw Error('Archiv nicht lesbar. Es wird nicht überschrieben. Roharchiv bitte zuerst sichern.');if(hasDrafts())throw Error('Ungültige Eingaben zuerst korrigieren oder rückgängig machen.');}
 function save(name){guard();snapshots=saveSnapshot(localStorage,snapshots,getProject(),name,newId());}
 function versions(){
  showDialog('Entwurfsstände',`<p>Lokales Archiv auf diesem Gerät. Ein Stand enthält den Entwurf, keine Berechnungsergebnisse. Exportiere das Archiv zur Sicherung.</p>${archiveError?'<div class="notice">Das vorhandene Archiv ist nicht lesbar und bleibt unverändert. Über „Archiv exportieren“ kannst du die Originaldaten sichern.</div>':''}<form id="snapshot-form" class="review-save"><label class="field"><span>Name des Entwurfsstands</span><input name="title" maxlength="120" required placeholder="z. B. Besprechung November"></label><button class="button button-primary" ${archiveError?'disabled':''}>Stand sichern</button></form><div class="review-actions"><button class="button" data-review="archive-export">Archiv exportieren</button><button class="button" data-review="archive-import" ${archiveError?'disabled':''}>Archiv importieren</button><input id="archive-file" type="file" accept=".json,application/json" hidden></div><p class="help-text">${snapshots.length} / 30 gespeicherte Stände · Vergleich jeweils gegen den aktuellen Entwurf</p><div class="snapshot-list">${snapshots.map(s=>`<article class="snapshot-card"><div><h3>${esc(s.name)}</h3><p>${esc(date(s.createdAt))} · ${s.project.nodes.length} Komponenten · ${s.project.edges.length} Verbindungen</p><small>${esc(s.project.name)}</small></div><div class="review-actions"><button class="button" data-compare="${s.id}">Vergleichen</button><button class="button" data-restore="${s.id}">Wiederherstellen</button><button class="button button-quiet" data-snapshot-export="${s.id}">Datei</button><button class="button button-quiet" data-snapshot-remove="${s.id}">Entfernen</button></div></article>`).join('')||'<div class="review-empty">Noch keine Stände. Sichere den aktuellen Entwurf mit einem Namen.</div>'}</div>`);
  document.querySelector('#snapshot-form').onsubmit=e=>{e.preventDefault();try{save(new FormData(e.target).get('title'));versions();toast('Entwurfsstand lokal gesichert.');}catch(err){toast(err.message);}};
 }
 function compare(id){
  const snapshot=snapshots.find(s=>s.id===id);if(!snapshot)return;
  const changes=documentChanges(snapshot.project,getProject());
  showDialog('Änderungsvergleich',`<p><strong>${esc(snapshot.name)}</strong> → aktueller Entwurf · ${changes.length} Änderungen</p><p class="help-text">Dokumentvergleich, keine Bewertung oder Rangfolge der Entwürfe. Positionsänderungen werden ebenfalls aufgeführt.</p>${changes.length?`<div class="table-scroll"><table class="review-table"><thead><tr><th>Bereich / Feld</th><th>Gespeichert</th><th>Aktuell</th></tr></thead><tbody>${changes.map(c=>`<tr><th>${esc(c.kind)}<br>${esc(c.label)}</th><td>${esc(value(c.before))}</td><td>${esc(value(c.after))}</td></tr>`).join('')}</tbody></table></div>`:'<div class="notice">Keine inhaltlichen Änderungen.</div>'}<button class="button" data-review="versions">Zurück zu Entwurfsständen</button>`);
 }
 function review(){
  const p=getProject(),r=getResult(),stale=isStale(),rows=componentReview(p,r,stale);
  showDialog('Modell- und Ergebnisstatus',`<div class="notice">${!r?'Noch keine Ergebnisse.':stale?'Ergebnisse gehören zu einem älteren Entwurfsstand.':r.ok?'Ergebnisse vorhanden. Das ist keine physikalische Validierung.':'Die Berechnung ist unvollständig.'}</div><p>Diese Übersicht zeigt vorhandene Daten und Meldungen. „Nicht bewertet“ bedeutet nicht automatisch fehlerhaft; manche Elemente haben keinen eigenen Ergebniseintrag.</p><div class="review-actions"><button class="button" data-review="report">Projektbericht herunterladen</button><button class="button" data-action="model">Modellgrenzen öffnen</button></div><ul class="review-components">${rows.map(n=>`<li><div><strong>${esc(n.label)}</strong><span class="badge">${esc(n.status)}</span></div>${n.messages.map(m=>`<p>${esc(m)}</p>`).join('')}<button class="button button-quiet" data-review-node="${esc(n.id)}">Komponente ansehen ↗</button></li>`).join('')}</ul>${r&&!stale&&(r.errors||[]).some(e=>!e.nodeId)?`<h3>Übergreifende Meldungen</h3><ul>${r.errors.filter(e=>!e.nodeId).map(e=>`<li>${esc(e.message)}</li>`).join('')}</ul>`:''}`);
 }
 function report(){
  const p=getProject(),r=getResult(),stale=isStale(),rows=componentReview(p,r,stale);
  const status=!r?'Nicht berechnet':stale?'Veralteter Ergebnisstand':r.ok?'Ergebnisse vorhanden · nicht physikalisch validiert':'Unvollständig';
  const html=`<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>${esc(p.name)} · Projektbericht</title><style>body{font:16px/1.6 system-ui;color:#172126;max-width:960px;margin:40px auto;padding:0 24px}h1{line-height:1.15}small{color:#536168}table{width:100%;border-collapse:collapse}td,th{padding:12px;border-bottom:1px solid #ccc;text-align:left;overflow-wrap:anywhere}aside{padding:16px;background:#f4f1e9}li{margin:8px 0}@media print{body{margin:0}tr{break-inside:avoid}}</style><header><small>ASTROFORGE 2.7 LITE · PROJEKTÜBERSICHT</small><h1>${esc(p.name)}</h1><p>Exportiert ${esc(date(new Date().toISOString()))}</p></header><aside><strong>${esc(status)}</strong><p>Dokumentationsbericht, kein Auslegungs- oder Validierungsnachweis. Rechenmodelle und Modellgrenzen wurden durch diese Produktversion nicht erweitert.</p></aside><p>${p.nodes.length} Komponenten · ${p.edges.length} Verbindungen</p><h2>Komponentenübersicht</h2><table><thead><tr><th>Komponente</th><th>Ergebnisstatus</th></tr></thead><tbody>${rows.map(n=>`<tr><td>${esc(n.label)}</td><td>${esc(n.status)}</td></tr>`).join('')}</tbody></table><h2>Meldungen des Ergebnisstands</h2>${stale?'<p>Veraltete Meldungen werden nicht als aktuelle Bewertung übernommen.</p>':`<ul>${[...(r?.errors||[]).map(e=>e.message),...(r?.warnings||[])].map(m=>`<li>${esc(m)}</li>`).join('')||'<li>Keine Meldungen vorhanden. Daraus folgt keine technische Freigabe.</li>'}</ul>`}<h2>Datenherkunft</h2><p>${esc(value(r?.meta?.source||r?.partial?.meta?.source||'Keine Ergebnisquelle vorhanden'))}</p><p>Für PDF im Browser „Drucken → Als PDF speichern“ wählen. Entwurfsdateien separat in AstroForge sichern.</p></html>`;
  download('astroforge-projektbericht.html',html,'text/html;charset=utf-8');
 }
 document.addEventListener('click',e=>{
  const button=e.target.closest('button');if(!button)return;
  try{
   const action=button.dataset.review;
   if(action==='versions')versions();if(action==='status')review();if(action==='report')report();
   if(action==='present')onPresentation();
   if(action==='archive-import'){
    const input=document.querySelector('#archive-file');
    input.onchange=async()=>{try{guard();const file=input.files[0];if(!file)return;if(file.size>2000000)throw Error('Archiv größer als 2 MB.');const raw=await file.text(),incoming=readJournal({getItem:()=>raw},parseProject);if(snapshots.length+incoming.length>30)throw Error('Das zusammengeführte Archiv hätte mehr als 30 Stände.');const merged=[...incoming.map(s=>({...s,id:newId()})),...snapshots];persist(merged);versions();toast(incoming.length+' Stände importiert. Aktuelles Projekt unverändert.');}catch(err){toast(err.message);}finally{input.value='';}};
    input.click();
   }
   if(action==='archive-export')download('astroforge-entwurfsarchiv.json',localStorage.getItem(JOURNAL_KEY)||'[]');
   if(button.dataset.compare)compare(button.dataset.compare);
   if(button.dataset.snapshotExport){const s=snapshots.find(s=>s.id===button.dataset.snapshotExport);if(s)download('astroforge-entwurfsstand.json',JSON.stringify(s.project,null,2));}
   if(button.dataset.restore){const s=snapshots.find(s=>s.id===button.dataset.restore);if(!s)return;showDialog('Entwurfsstand wiederherstellen',`<p>„${esc(s.name)}“ öffnen? Der aktuelle Entwurf wird zuvor automatisch als Sicherung archiviert. Ergebnisse werden verworfen und nicht als aktuell übernommen.</p><button class="button button-primary" data-confirm-restore="${s.id}">Sichern und wiederherstellen</button><button class="button" data-review="versions">Abbrechen</button>`);}
   if(button.dataset.confirmRestore){const s=snapshots.find(s=>s.id===button.dataset.confirmRestore);if(!s)return;const restored=parseProject(JSON.stringify(s.project));save('Sicherung vor Wiederherstellung');replaceProject(restored);dialog().close();toast('Stand wiederhergestellt. Aktueller Entwurf als Sicherung behalten.');}
   if(button.dataset.snapshotRemove){const s=snapshots.find(s=>s.id===button.dataset.snapshotRemove);if(!s)return;showDialog('Stand entfernen',`<p>„${esc(s.name)}“ aus dem lokalen Archiv entfernen? Exportiere den Stand bei Bedarf vorher.</p><button class="button" data-snapshot-export="${s.id}">Datei sichern</button><button class="button" data-confirm-remove="${s.id}">Stand entfernen</button><button class="button" data-review="versions">Abbrechen</button>`);}
   if(button.dataset.confirmRemove){persist(snapshots.filter(s=>s.id!==button.dataset.confirmRemove));versions();}
   if(button.dataset.reviewNode){dialog().close();document.dispatchEvent(new CustomEvent('review-select',{detail:button.dataset.reviewNode}));}
  }catch(err){toast(err.message||'Aktion konnte nicht gespeichert werden.');}
 });
 return {versions,review,report};
}
