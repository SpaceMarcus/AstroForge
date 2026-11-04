import test from 'node:test';
import assert from 'node:assert/strict';
import {coolingResults, CHANNEL_FIELDS, CHANNEL_DEFAULTS} from '../src/cooling-ui.js';
import {cycleResults} from '../src/cycle-ui.js';

const esc=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(value,digits=2)=>Number(value).toFixed(digits);
const station=(xM,hot)=>({xM,radiusM:0.04,mach:1,gasRecoveryTemperatureK:3300,coolantTemperatureK:320+xM*10,coolantPressureBar:40+xM,hotWallTemperatureK:hot,coldWallTemperatureK:hot-150,heatFluxWm2:2e6+xM*1e6,gasHTCWm2K:3000,coolantHTCWm2K:6000,reynolds:8000,channelWidthMm:1.2,velocityMS:12});
const channel={nodeId:'regen',mode:'channels',heatKW:50,dropBar:2,inletTemperatureK:293.15,outletTemperatureK:330,massFlowKgS:1.2,inletPressureBar:42,outletPressureBar:40,maxHotWallTemperatureK:850,maxHeatFluxWm2:3e6,wallMarginK:50,feasible:true,throatX:0.5,energyResidualW:0.0001,stations:[station(0,700),station(0.5,850),station(1,760)]};
const result={ok:true,cycle:{cooling:[channel]}};

test('only channel calculations generate axial profiles',()=>{
  assert.equal(coolingResults({ok:false},esc,fmt),'');
  assert.equal(coolingResults({ok:true,cycle:{cooling:[{nodeId:'old',heatKW:50}]}},esc,fmt),'');
  assert.equal(coolingResults({ok:true,cycle:{cooling:[{...channel,stations:[]}]}},esc,fmt),'');
});

test('default inspection targets the thermal peak and shows all three temperature series',()=>{
  const html=coolingResults(result,esc,fmt);
  assert.ok(html.includes('STATION 2 / 3'));
  assert.ok(html.includes('Heiße Wand'));
  assert.ok(html.includes('Kalte Wand'));
  assert.ok(html.includes('Kühlmittel'));
  assert.ok(html.includes('Düsenhals'));
  assert.ok(html.includes('900 K'));
  assert.ok(html.includes('keine geprüfte Werkstoffzulässigkeit'));
  assert.ok(!html.includes('NaN'));
  assert.ok(!html.includes('Infinity'));
});

test('station and quantity controls expose stable scoped actions',()=>{
  const html=coolingResults(result,esc,fmt,{}, {regen:{view:'heatflux',station:0}});
  assert.ok(html.includes('STATION 1 / 3'));
  assert.ok(html.includes('data-cooling-view="heatflux" data-cooling-node="regen" aria-pressed="true"'));
  assert.ok(html.includes('data-cooling-station="regen"'));
  assert.ok(html.includes('data-cooling-index="2" data-cooling-node="regen"'));
  assert.ok(html.includes('data-action="cooling-csv" data-cooling-node="regen"'));
  assert.ok(html.includes('MW/m²'));
  const pressure=coolingResults(result,esc,fmt,{}, {regen:{view:'pressure',station:2}});
  assert.ok(pressure.includes('STATION 3 / 3'));
  assert.ok(pressure.includes('Kühlmitteldruck'));
});

test('temperature limit exceedance remains explicit even with numerically valid result',()=>{
  const html=coolingResults({ok:true,cycle:{cooling:[{...channel,wallMarginK:-20,feasible:false}]}},esc,fmt);
  assert.ok(html.includes('WANDGRENZE ÜBERSCHRITTEN'));
  assert.ok(html.includes('-20'));
  assert.ok(html.includes('keine zertifizierte Kühlung'));
});

test('project labels are escaped and invalid UI selection falls back to the peak',()=>{
  const html=coolingResults(result,esc,fmt,{regen:'<img src=x onerror=alert(1)>'},{regen:{view:'__proto__',station:999}});
  assert.ok(html.includes('&lt;img'));
  assert.ok(!html.includes('<img'));
  assert.ok(html.includes('STATION 2 / 3'));
  assert.ok(html.includes('data-cooling-view="temperature" data-cooling-node="regen" aria-pressed="true"'));
});

test('mixed legacy and channel results retain distinct model descriptions',()=>{
  const html=cycleResults({ok:true,cycle:{cooling:[channel,{nodeId:'old',heatKW:20,dropBar:1,cpJkgK:2200,inletTemperatureK:290,outletTemperatureK:300,massFlowKgS:1}]}},esc,fmt,{}, {regen:{station:2}});
  assert.ok(html.includes('WÄRMEAUFNAHME · VORGABEMODELL'));
  assert.ok(html.includes('REGENERATIV / KANALMODELL'));
  assert.ok(html.includes('STATION 3 / 3'));
});

test('all shared defaults satisfy field ranges and discrete counts are integral',()=>{
  assert.equal(CHANNEL_DEFAULTS.mode,'channels');
  for(const field of CHANNEL_FIELDS){
    const value=CHANNEL_DEFAULTS[field.key];
    assert.ok(Number.isFinite(value)&&value>=field.min&&value<=field.max,field.key);
  }
  assert.ok(Number.isInteger(CHANNEL_DEFAULTS.channelCount));
  assert.ok(Number.isInteger(CHANNEL_DEFAULTS.stations));
  assert.ok(!Object.hasOwn(CHANNEL_DEFAULTS,'heatKW'));
  assert.ok(!Object.hasOwn(CHANNEL_DEFAULTS,'dropBar'));
});


test('zero-volume boundary stations remain visible and can hold the hottest wall',()=>{
  const boundary={...station(1,950),segmentHeatW:0,frictionDropBar:0,accelerationDropBar:0};
  const updated={...channel,maxHotWallTemperatureK:950,wallMarginK:-50,feasible:false,stations:[station(0,700),station(.5,850),boundary]};
  const html=coolingResults({ok:true,cycle:{cooling:[updated]}},esc,fmt);
  assert.ok(html.includes('STATION 3 / 3'));
  assert.ok(html.includes('950<small>K</small>'));
  assert.ok(html.includes('WANDGRENZE ÜBERSCHRITTEN'));
  assert.ok(html.includes('data-cooling-index="2"'));
  assert.ok(!html.includes('NaN'));
  assert.ok(!html.includes('Infinity'));
});
