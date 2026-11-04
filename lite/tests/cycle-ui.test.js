import test from 'node:test';
import assert from 'node:assert/strict';
import {cycleResults, COMPONENT_FIELDS, COMPONENT_NOTES} from '../src/cycle-ui.js';

const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = (value, decimals = 2) => Number(value).toFixed(decimals);
const shaft = {
  nodeId:'shaft-1',rpm:25000,efficiency:0.95,motorKW:0,turbinePowerKW:10,
  availablePowerKW:9.5,requiredPowerKW:12,balanceKW:-2.5,
  requiredTorqueNm:4.58,availableTorqueNm:3.63,feasible:false,
};

test('cycle panel is absent for invalid or ordinary pressure-fed results', () => {
  assert.equal(cycleResults(null, esc, fmt), '');
  assert.equal(cycleResults({ok:false,cycle:{shafts:[shaft]}}, esc, fmt), '');
  assert.equal(cycleResults({ok:true,cycle:{pumps:[],shafts:[],turbines:[],cooling:[]}}, esc, fmt), '');
});

test('deficit is explicit and escaped project labels never become markup', () => {
  const html=cycleResults({ok:true,cycle:{shafts:[shaft]}}, esc, fmt, {'shaft-1':'<img src=x onerror=alert(1)>'});
  assert.ok(html.includes('LEISTUNG FEHLT'));
  assert.ok(html.includes('Leistungsdefizit'));
  assert.ok(html.includes('2.50 kW'));
  assert.ok(html.includes('&lt;img'));
  assert.ok(!html.includes('<img'));
  assert.ok(html.includes('width:79.16666666666666%'));
  assert.ok(!html.includes('NaN'));
});

test('shaft reserve does not claim a solved shaft equilibrium', () => {
  const html=cycleResults({ok:true,cycle:{shafts:[{...shaft,availablePowerKW:20,balanceKW:8,feasible:true}]}}, esc, fmt);
  assert.ok(html.includes('LEISTUNG AUSREICHEND'));
  assert.ok(html.includes('Leistungsreserve'));
  assert.ok(html.includes('kein gelöster Drehzahlgleichgewichtspunkt'));
  assert.ok(html.includes('width:100%'));
});

test('auxiliary massflow appears alongside total system performance and model limit', () => {
  const auxiliary={sourceId:'gas',turbineId:'t',exhaustId:'ex',massFlowKgS:0.2,exitPressureBar:1.01,exitTemperatureK:400,exitVelocityMS:800,exitAreaM2:0.001,thrustN:160,systemThrustN:10160,totalMassFlowKgS:4.2,systemIspS:246.7};
  const html=cycleResults({ok:true,cycle:{auxiliary}}, esc, fmt);
  assert.ok(html.includes('System-Isp'));
  assert.ok(html.includes('246.7'));
  assert.ok(html.includes('4.200 kg/s'));
  assert.ok(html.includes('vollständiger Cycle-Abschluss sind nicht gelöst'));
});

test('new component inspector metadata covers bounded fields and caveats', () => {
  for (const [type,fields] of Object.entries(COMPONENT_FIELDS)) {
    assert.ok(COMPONENT_NOTES[type]);
    for (const field of fields) {
      assert.ok(field.min<field.max, `${type}.${field.key}`);
      assert.ok(field.step>0);
      assert.ok(field.label && field.unit);
    }
  }
  assert.equal(COMPONENT_FIELDS.pump.find(f=>f.key==='riseBar').max,150);
  assert.equal(COMPONENT_FIELDS.gasSource.find(f=>f.key==='temperatureK').max,2000);
  assert.equal(COMPONENT_FIELDS.exhaust.find(f=>f.key==='exitBar').min,0.001);
});
