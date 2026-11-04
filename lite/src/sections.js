export const ENGINE_TYPES=['injector','chamber','nozzle'];
export function sectionOf(node){
 if(ENGINE_TYPES.includes(node.type))return 'engine';
 if(node.type==='regen'||node.type==='coolantSource')return 'cooling';
 return node.section||null;
}
