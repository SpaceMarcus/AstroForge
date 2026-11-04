export function coolingParams(project,node){
 const p={...node.params},direction=p.flowDirection??'counter';
 const inlet=project.edges.find(e=>e.to===node.id),outlet=project.edges.find(e=>e.from===node.id);
 for(const [edge,end] of [[inlet,'inlet'],[outlet,'outlet']]){
  const other=project.nodes.find(n=>n.id===(end==='inlet'?edge?.from:edge?.to));
  if(other?.type==='manifold'&&Number.isFinite(other.params.axialPosition)){
   const key=(end==='inlet')===(direction==='co')?'coolingStart':'coolingEnd';p[key]=other.params.axialPosition;p[key+'Locked']=true;
  }
 }
 return p;
}
export function contourPosition(geometry,fraction){
 const contour=geometry?.contour;if(!contour?.length||!Number.isFinite(fraction))return null;
 const x=fraction*contour.at(-1).x;let i=0;while(i<contour.length-2&&x>contour[i+1].x)i++;
 const a=contour[i],b=contour[i+1],r=a.r+(b.r-a.r)*(x-a.x)/(b.x-a.x),throat=contour.reduce((u,v)=>v.r<u.r?v:u);
 return {xM:x,epsilon:(r/geometry.throatRadiusM)**2,region:x<throat.x?'vor Hals':x>throat.x?'nach Hals':'Hals'};
}
