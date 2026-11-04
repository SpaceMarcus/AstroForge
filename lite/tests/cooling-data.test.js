import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const data = JSON.parse(readFileSync(new URL('../public/cooling-data.json', import.meta.url), 'utf8'));
const coolant = data.coolant;

test('offline cooling data declares the real surrogate and consistent SI grids', () => {
  assert.equal(data.format, 'astroforge-cooling-data');
  assert.equal(coolant.surrogate, true);
  assert.equal(coolant.fluid, 'n-Dodecane');
  assert.match(coolant.displayName, /not actual RP-1/);
  assert.equal(coolant.values.length, coolant.axes.temperatureK.length);
  for (const [i, row] of coolant.values.entries()) {
    assert.equal(row.length, coolant.axes.pressureBar.length);
    assert.equal(coolant.phases[i].length, row.length);
    for (const [j, state] of row.entries()) {
      if (state === null) {
        assert.ok(!coolant.validity.allowedPhases.includes(coolant.phases[i][j]));
      } else {
        assert.equal(state.length, coolant.columns.length);
        assert.ok(state.every(Number.isFinite));
        assert.ok(state.slice(0, 4).every(value => value > 0));
        assert.ok(coolant.validity.allowedPhases.includes(coolant.phases[i][j]));
      }
    }
  }
});

test('low-pressure vapor cells are absent rather than clamped to liquid data', () => {
  const lowPressure = coolant.axes.pressureBar.indexOf(1);
  assert.ok(coolant.values[0][lowPressure]);
  assert.equal(coolant.values.at(-1)[lowPressure], null);
  assert.ok(coolant.values.at(-1)[coolant.axes.pressureBar.indexOf(100)]);
});

test('enthalpy rises with temperature and agrees with the heat capacity integral at constant pressure', () => {
  const h = coolant.columns.indexOf('hJkg'), cp = coolant.columns.indexOf('cpJkgK');
  let comparisons = 0;
  for (let i = 0; i < coolant.axes.temperatureK.length - 1; i++) {
    const dt = coolant.axes.temperatureK[i + 1] - coolant.axes.temperatureK[i];
    for (let j = 0; j < coolant.axes.pressureBar.length; j++) {
      const a = coolant.values[i][j], b = coolant.values[i + 1][j];
      if (!a || !b) continue;
      const dh = b[h] - a[h];
      assert.ok(dh > 0, `Enthalpy must rise at ${i}, ${j}`);
      const cpIntegral = dt * (a[cp] + b[cp]) / 2;
      assert.ok(Math.abs(cpIntegral / dh - 1) < .03, `cp and enthalpy disagree at ${i}, ${j}`);
      comparisons++;
    }
  }
  assert.ok(comparisons > 400);
});

test('CEA chamber transport preserves SI Prandtl closure and the validated pressure/mixture range', () => {
  const gas = data.gas;
  assert.equal(gas.axes.pcBar[0], 10);
  assert.equal(gas.axes.pcBar.at(-1), 80);
  assert.equal(gas.axes.of[0], 2);
  assert.equal(gas.axes.of.at(-1), 3.2);
  assert.equal(gas.values.length, gas.axes.pcBar.length);
  for (const row of gas.values) {
    assert.equal(row.length, gas.axes.of.length);
    for (const state of row) {
      const fields = Object.fromEntries(gas.columns.map((name, i) => [name, state[i]]));
      assert.ok(state.every(value => Number.isFinite(value) && value > 0));
      assert.ok(fields.gamma > 1 && fields.gamma < 2);
      const prFromTransport = fields.cpJkgK * fields.muPaS / fields.kWmK;
      assert.ok(Math.abs(prFromTransport / fields.prandtl - 1) < .005);
      const prFrozen = fields.cpFrozenJkgK * fields.muPaS / fields.kFrozenWmK;
      assert.ok(Math.abs(prFrozen / fields.prandtlFrozen - 1) < .005);
      assert.ok(fields.gammaFrozen > 1 && fields.gammaFrozen < 2);
    }
  }
});

test('grid generation documents sampled error rather than claiming physical RP-1 validation', () => {
  assert.ok(data.gas.validation.sampleCount >= 40);
  assert.ok(coolant.validation.sampleCount >= 400);
  assert.ok(coolant.validation.maxSampledRelativeError.muPaS < .01);
  assert.ok(coolant.validation.maxSampledRelativeError.cpJkgK < .01);
  assert.ok(coolant.validation.legacyPropertyAdapterKnotComparisons.every(row => row.maxRelativeDifferenceFirstFourProperties < 1e-6));
  assert.match(coolant.validation.limitation, /no evidence of RP-1/);
});
