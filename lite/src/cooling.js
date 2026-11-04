/** Steady 1-D counterflow screening. Fixed CEA gas boundary; no chemistry feedback. */
export const CHANNEL_BOUNDS={channelCount:[12,500],channelHeightMm:[.2,10],channelWidthFraction:[.1,.9],wallThicknessMm:[.2,5],wallConductivityWmK:[5,500],roughnessMm:[0,.1],minorK:[0,50],wallLimitK:[400,2000],stations:[40,400],throatCurvatureRatio:[.2,5]};
export async function loadCoolingData(){const r=await fetch(new URL('../cooling-data.json',import.meta.url));if(!r.ok)throw new Error('Kühlungsstoffdaten konnten nicht geladen werden.');return r.json();}
function bracket(a,x,label){if(!Array.isArray(a)||a.length<2||!Number.isFinite(x)||x<a[0]||x>a.at(-1))throw new Error(`${label}=${Number(x).toFixed(2)}: außerhalb der Stoffdatentabelle.`);let i=0;while(i<a.length-2&&x>a[i+1])i++;return [i,(x-a[i])/(a[i+1]-a[i])];}
function interpolate(table,x,y,axes){if(!table)throw new Error('Kühlungsstoffdaten fehlen.');const [i,u]=bracket(table.axes[axes[0]],x,axes[0]),[j,v]=bracket(table.axes[axes[1]],y,axes[1]);const result={};for(let k=0;k<table.columns.length;k++){let value=0;for(let a=0;a<2;a++)for(let b=0;b<2;b++){const w=(a?u:1-u)*(b?v:1-v);if(w===0)continue;const cell=table.values[i+a]?.[j+b];if(!cell||!Number.isFinite(cell[k]))throw new Error('Kühlmittel: ungültige Phase oder fehlende Stoffdaten im Interpolationsbereich.');value+=w*cell[k];}result[table.columns[k]]=value;}return result;}
export function coolantAt(data,temperatureK,pressureBar){const p=interpolate(data?.coolant,temperatureK,pressureBar,['temperatureK','pressureBar']);for(const key of ['rhoKgM3','cpJkgK','muPaS','kWmK'])if(!(p[key]>0))throw new Error('Ungültige Kühlmittelstoffwerte.');return p;}
export function staticPressureAt(data,temperatureK,totalPressureBar,areaM2,massFlowKgS){let pressure=totalPressureBar;for(let i=0;i<40;i++){const f=coolantAt(data,temperatureK,pressure),next=totalPressureBar-massFlowKgS**2/(2*f.rhoKgM3*areaM2**2)/1e5;if(Math.abs(next-pressure)<1e-9)return next;pressure=next;}throw new Error('Umrechnung Gesamt-/Statikdruck konvergiert nicht.');}
export function gasAt(data,pcBar,of){const p=interpolate(data?.gas,pcBar,of,['pcBar','of']);if(!(p.gamma>1&&p.cpJkgK>0&&p.muPaS>0&&p.prandtl>0))throw new Error('Ungültige Gastransportdaten.');return p;}
export function channelTransport(re,pr,width,height,roughness){
 const dh=2*width*height/(width+height),a=Math.min(width,height)/Math.max(width,height);
 if(!(re>0&&pr>0&&width>0&&height>0&&roughness>=0&&roughness/dh<=.05))throw new Error('Kanalgeometrie/Rauheit außerhalb des Korrelationsbereichs.');
 const fl=96*(1-1.3553*a+1.9467*a*a-1.7012*a**3+.9564*a**4-.2537*a**5)/re;
 const ft=(-1.8*Math.log10((roughness/(3.7*dh))**1.11+6.9/re))**-2,t=Math.max(0,Math.min(1,(re-2300)/1700));
 const f=fl+(ft-fl)*t,nul=8.235*(1-2.0421*a+3.0853*a*a-2.4765*a**3+1.0578*a**4-.1861*a**5);
 const nut=(f/8)*(re-1000)*pr/(1+12.7*Math.sqrt(f/8)*(pr**(2/3)-1));
 return {darcy:f,nusselt:nul+(nut-nul)*t,hydraulicDiameterM:dh,transition:re>2300&&re<4000,outside:re>5e6||pr<.5||pr>2000};
}
export function machFromArea(areaRatio,gamma,supersonic){if(areaRatio<1||gamma<=1)throw new Error('Ungültiges Düsenflächenverhältnis.');if(areaRatio-1<1e-10)return 1;let lo=supersonic?1:1e-8,hi=supersonic?30:1;for(let i=0;i<80;i++){const m=(lo+hi)/2,a=(1/m)*(2/(gamma+1)*(1+(gamma-1)*m*m/2))**((gamma+1)/(2*(gamma-1)));if((a>areaRatio)===supersonic)hi=m;else lo=m;}return (lo+hi)/2;}
export function bartzHTC({gas,pcBar,cstarMS,tcK,throatRadiusM,curvatureRatio,areaRatio,mach,wallTemperatureK}){const z=1+(gas.gamma-1)*mach*mach/2,sigma=(.5*wallTemperatureK/tcK*z+.5)**-.68*z**-.12;return .026*gas.muPaS**.2*gas.cpJkgK/gas.prandtl**.6*(pcBar*1e5/cstarMS)**.8*(2*throatRadiusM)**-.2*(2/curvatureRatio)**.1*areaRatio**-.9*sigma;}
function radiusAt(contour,x){let i=0;while(i<contour.length-2&&x>contour[i+1].x)i++;const a=contour[i],b=contour[i+1];return a.r+(b.r-a.r)*(x-a.x)/(b.x-a.x);}
export function solveCooling({params:p,geometry:g,design,thermo,data,massFlowKgS:mdot,inletTemperatureK,inletPressureBar}){
 for(const [key,[min,max]] of Object.entries(CHANNEL_BOUNDS))if(!Number.isFinite(p[key])||p[key]<min||p[key]>max||(['stations','channelCount'].includes(key)&&!Number.isInteger(p[key])))throw new Error(`Kühlkanal ${key}: erwartet ${min}–${max}.`);
 if(!(mdot>0)||!g.contour?.length)throw new Error('Ungültiger Kühlmassenstrom oder Kontur.');
 if(!Number.isFinite(mdot)||!Number.isFinite(g.throatRadiusM)||g.throatRadiusM<=0||g.contour.some((s,i)=>!Number.isFinite(s.x)||!Number.isFinite(s.r)||s.r<=0||(i>0&&s.x<=g.contour[i-1].x)))throw new Error('Ungültige Kühlkontur: positive Radien und streng steigende Axialkoordinaten erforderlich.');
 const gasTable=gasAt(data,design.pcBar,design.of),gas={...gasTable,cpJkgK:gasTable.cpFrozenJkgK,prandtl:gasTable.prandtlFrozen,gamma:gasTable.gammaFrozen};
 if(!(gas.cpJkgK>0&&gas.prandtl>0&&gas.gamma>1))throw new Error('Frozen-Gastransportdaten fehlen.');
 const height=p.channelHeightMm/1000,wall=p.wallThicknessMm/1000,kw=p.wallConductivityWmK;
 const throatX=g.contour.reduce((a,b)=>b.r<a.r?b:a).x,end=g.contour.at(-1).x;
 // Include all geometry breakpoints as well as a uniform refinement: exactly the displayed contour.
 const xs=[...new Set([...g.contour.map(v=>v.x),...Array.from({length:p.stations+1},(_,i)=>i*end/p.stations)])].sort((a,b)=>a-b);
 const section=x=>{const r=radiusAt(g.contour,x),pitch=2*Math.PI*(r+wall+height/2)/p.channelCount,width=pitch*p.channelWidthFraction;return {r,pitch,width,area:width*height*p.channelCount};};
 const inletStaticPressureBar=staticPressureAt(data,inletTemperatureK,inletPressureBar,section(end).area,mdot);
 let temperature=inletTemperatureK,pressure=inletStaticPressureBar,heatW=0;const start=coolantAt(data,temperature,pressure),startV=mdot/(start.rhoKgM3*section(end).area),stations=[],warnings=new Set();
 const wallState=(x,tm,pm)=>{
  const s=section(x),ar=(s.r/g.throatRadiusM)**2,mach=machFromArea(ar,gas.gamma,x>throatX),z=1+(gas.gamma-1)*mach*mach/2,recovery=thermo.tcK/z*(1+gas.prandtl**(1/3)*(z-1));
  const f=coolantAt(data,tm,pm),velocity=mdot/(f.rhoKgM3*s.area),dh=2*s.width*height/(s.width+height),re=f.rhoKgM3*velocity*dh/f.muPaS,pr=f.cpJkgK*f.muPaS/f.kWmK;
  const tr=channelTransport(re,pr,s.width,height,p.roughnessMm/1000),hc=tr.nusselt*f.kWmK/dh,rib=s.pitch-s.width;
  // Straight rectangular rib, referenced to hot-side circumference (no roof convection).
  const mh=Math.sqrt(2*hc/(kw*rib))*height,fin=Math.tanh(mh)/mh,areaFactor=p.channelCount*(s.width+2*height*fin)/(2*Math.PI*s.r);
  const resistance=wall/kw+1/(hc*areaFactor);let low=tm,high=recovery;
  if(!(high>low))throw new Error('Kühlmittel heißer als lokale Gas-Recoverytemperatur.');
  for(let k=0;k<60;k++){const tw=(low+high)/2,hg=bartzHTC({gas,pcBar:design.pcBar,cstarMS:thermo.cstarMS,tcK:thermo.tcK,throatRadiusM:g.throatRadiusM,curvatureRatio:p.throatCurvatureRatio,areaRatio:ar,mach,wallTemperatureK:tw});if(hg*(recovery-tw)>(tw-tm)/resistance)low=tw;else high=tw;}
  const tw=(low+high)/2,q=(tw-tm)/resistance;
  if(tr.transition)warnings.add('Übergangsströmung: Wärmeübergang und Reibung interpoliert.');if(tr.outside)warnings.add('Gnielinski außerhalb des empfohlenen Re/Pr-Bereichs.');
  return {f,tr,dh,velocity,profile:{xM:x,radiusM:s.r,mach,gasRecoveryTemperatureK:recovery,coolantTemperatureK:tm,coolantPressureBar:pm,hotWallTemperatureK:tw,coldWallTemperatureK:tw-q*wall/kw,heatFluxWm2:q,gasHTCWm2K:q/(recovery-tw),coolantHTCWm2K:hc,reynolds:re,channelWidthMm:s.width*1000,velocityMS:velocity}};
 };
 const addBoundary=(x,t,p)=>stations.push({...wallState(x,t,p).profile,sampleKind:'boundary',segmentHeatW:0,frictionDropBar:0,accelerationDropBar:0});
 addBoundary(end,temperature,pressure);
 for(let i=xs.length-1;i>0;i--){
  const x0=xs[i],x1=xs[i-1],x=(x0+x1)/2,s=section(x),a=section(x0),b=section(x1),ds=Math.hypot(x0-x1,a.r-b.r),hotArea=2*Math.PI*s.r*ds;
  const pin=pressure,tin=temperature,fluidIn=coolantAt(data,tin,pin),vin=mdot/(fluidIn.rhoKgM3*a.area);
  let tout=tin,pout=pin,record,converged=false;
  for(let iteration=0;iteration<100;iteration++){
   const tm=(tin+tout)/2,pm=(pin+pout)/2,local=wallState(x,tm,pm),{f,tr,dh,velocity}=local;
   const Q=local.profile.heatFluxWm2*hotArea,fo=coolantAt(data,tout,pout),vout=mdot/(fo.rhoKgM3*b.area);
   const loss=(tr.darcy*ds/dh+p.minorK*(x0-x1)/end)*f.rhoKgM3*velocity*velocity/2;
   // Momentum acceleration integral; variable area may yield static pressure recovery.
   const acceleration=(fluidIn.rhoKgM3+fo.rhoKgM3)/2*(vout*vout-vin*vin)/2;
   const nextP=pin-(loss+acceleration)/1e5;
   const targetH=fluidIn.hJkg+Q/mdot+(vin*vin-vout*vout)/2;
   const nextT=tout+(targetH-fo.hJkg)/fo.cpJkgK;
   record={...local.profile,sampleKind:'cell',segmentHeatW:Q,frictionDropBar:loss/1e5,accelerationDropBar:acceleration/1e5};
   if(Math.abs(nextT-tout)<1e-6&&Math.abs(nextP-pout)<1e-7){tout=nextT;pout=nextP;converged=true;break;}
   tout=.5*(tout+nextT);pout=.5*(pout+nextP);
  }
  if(!converged)throw new Error('Kühlkanaliteration konvergiert nicht.');
  coolantAt(data,tout,pout);temperature=tout;pressure=pout;heatW+=record.segmentHeatW;stations.push(record);addBoundary(x1,temperature,pressure);
 }
 const finish=coolantAt(data,temperature,pressure),finishV=mdot/(finish.rhoKgM3*section(0).area),maxHotWallTemperatureK=Math.max(...stations.map(s=>s.hotWallTemperatureK));
 const outletPressureBar=pressure+finish.rhoKgM3*finishV**2/2/1e5;
 return {mode:'channels',heatKW:heatW/1000,dropBar:inletPressureBar-outletPressureBar,inletTemperatureK,outletTemperatureK:temperature,inletPressureBar,outletPressureBar,inletStaticPressureBar,outletStaticPressureBar:pressure,massFlowKgS:mdot,maxHotWallTemperatureK,maxHeatFluxWm2:Math.max(...stations.map(s=>s.heatFluxWm2)),wallMarginK:p.wallLimitK-maxHotWallTemperatureK,feasible:maxHotWallTemperatureK<=p.wallLimitK,throatX,energyResidualW:heatW-mdot*(finish.hJkg-start.hJkg+(finishV*finishV-startV*startV)/2),stations:stations.reverse(),warnings:[...warnings]};
}
