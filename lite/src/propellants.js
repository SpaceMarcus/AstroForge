// Explicit supported combinations; old projects without a selection remain LOX/RP-1.
export const FLUID_CATALOG={
 'rp1':{label:'RP-1',temperatureK:293.15,tMin:288,tMax:303},
 'methane':{label:'Methan · flüssig',temperatureK:110,tMin:105,tMax:115},
 'hydrogen':{label:'Wasserstoff · flüssig',temperatureK:20,tMin:18,tMax:22},
 'ethanol':{label:'Ethanol · rein',temperatureK:293.15,tMin:288,tMax:303},
 'propane':{label:'Propan · flüssig',temperatureK:230,tMin:225,tMax:235},
 'lox':{label:'LOX',temperatureK:90,tMin:85,tMax:95},
 'n2o':{label:'Lachgas · flüssig',temperatureK:250,tMin:245,tMax:255},
 'htp90':{label:'HTP · 90 Gew.-% H₂O₂',temperatureK:293.15,tMin:288,tMax:303},
};
const pair=(id,label,fuel,ox,of,defaultOf)=>({id,label,fuel,ox,of,defaultOf,channelCooling:['rp1','ethanol'].includes(fuel)});
export const PROPELLANT_PAIRS=[
 pair('lox-rp1','LOX / RP-1','rp1','lox',[2,3.2],2.6),
 pair('lox-methane','LOX / Methan','methane','lox',[2.5,4],3.2),
 pair('lox-hydrogen','LOX / Wasserstoff','hydrogen','lox',[4,7],5.5),
 pair('lox-ethanol','LOX / Ethanol','ethanol','lox',[1.2,2],1.6),
 pair('lox-propane','LOX / Propan','propane','lox',[2,3.5],2.8),
 pair('n2o-rp1','N₂O / RP-1','rp1','n2o',[4,8],6),
 pair('n2o-ethanol','N₂O / Ethanol','ethanol','n2o',[3,6],4.5),
 pair('n2o-propane','N₂O / Propan','propane','n2o',[4,9],6.5),
 pair('htp90-rp1','HTP 90 % / RP-1','rp1','htp90',[5,9],7),
 pair('htp90-ethanol','HTP 90 % / Ethanol','ethanol','htp90',[3.5,6.5],5),
 pair('htp90-propane','HTP 90 % / Propan','propane','htp90',[5,10],7.5),
];
export function getPair(design){const id=design?.propellantPair??'lox-rp1';const pair=PROPELLANT_PAIRS.find(p=>p.id===id);if(!pair)throw Error('Unbekannte Treibstoffkombination: '+id);return pair;}
export function getFluid(id){const fluid=FLUID_CATALOG[id];if(!fluid)throw Error('Unbekannter Stoff: '+id);return fluid;}
export function changePropellantPair(project,id){
 const pair=getPair({propellantPair:id}),previous=getPair(project.design);
 project.design.propellantPair=id;project.design.of=pair.defaultOf;
 for(const n of project.nodes){
  if(!['fuel','ox'].includes(n.medium))continue;
  const fluid=getFluid(pair[n.medium]),old=getFluid(previous[n.medium]);
  if(['source','coolantSource'].includes(n.type))n.params.temperatureK=fluid.temperatureK;
  // Only generated labels change; custom labels remain user-owned.
  for(const suffix of [' Versorgung',' Pumpe'])if(n.label===old.label+suffix||n.label===(previous[n.medium]==='rp1'?'RP-1':old.label)+suffix)n.label=fluid.label+suffix;
  if(n.label==='Separate '+old.label+'-Kühlversorgung')n.label='Separate '+fluid.label+'-Kühlversorgung';
 }
 return project;
}
