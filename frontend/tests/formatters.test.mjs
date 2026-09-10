import test from 'node:test'
import assert from 'node:assert/strict'

import { fmtIP } from '../src/utils/formatters.js'

test('formats decimal innings in baseball notation', () => {
  assert.equal(fmtIP(2 + 2 / 3), '2.2')
  assert.equal(fmtIP(1.0), '1.0')
  assert.equal(fmtIP(1 / 3), '0.1')
})

test('formats aggregate innings by rounded total outs', () => {
  assert.equal(fmtIP((2 + 2 + 2) / 3), '2.0')
  assert.equal(fmtIP((8 + 1) / 3), '3.0')
})

test('formats innings directly from outs when available', () => {
  assert.equal(fmtIP(2.6666666667, 8), '2.2')
  assert.equal(fmtIP(0.3333333333, 1), '0.1')
})
