import {solveProject} from './physics.js';
self.onmessage = ({data}) => { try { self.postMessage({id:data.id,result:solveProject(data.project,data.thermo,data.coolingData)}); } catch(error) {self.postMessage({id:data.id,result:{ok:false,errors:[{message:error.message}],warnings:[]}});} };
