import assert from 'node:assert/strict'
import test from 'node:test'

import tailwindConfig from '../tailwind.config.js'

function channelToLinear(channel) {
  const value = channel / 255
  return value <= 0.03928
    ? value / 12.92
    : Math.pow((value + 0.055) / 1.055, 2.4)
}

function luminance(hex) {
  const value = hex.replace('#', '')
  const red = Number.parseInt(value.slice(0, 2), 16)
  const green = Number.parseInt(value.slice(2, 4), 16)
  const blue = Number.parseInt(value.slice(4, 6), 16)
  return (
    0.2126 * channelToLinear(red)
    + 0.7152 * channelToLinear(green)
    + 0.0722 * channelToLinear(blue)
  )
}

function contrastRatio(foreground, background) {
  const foregroundLum = luminance(foreground)
  const backgroundLum = luminance(background)
  const lighter = Math.max(foregroundLum, backgroundLum)
  const darker = Math.min(foregroundLum, backgroundLum)
  return (lighter + 0.05) / (darker + 0.05)
}

function blendHex(foreground, background, alpha) {
  const channels = hex => [1, 3, 5].map(index => Number.parseInt(hex.slice(index, index + 2), 16))
  const foregroundChannels = channels(foreground)
  const backgroundChannels = channels(background)
  const blended = foregroundChannels.map((value, index) => (
    Math.round(value * alpha + backgroundChannels[index] * (1 - alpha))
  ))
  return `#${blended.map(value => value.toString(16).padStart(2, '0')).join('')}`
}

test('muted chalk text tokens meet WCAG AA on dark surfaces', () => {
  const colors = tailwindConfig.theme.extend.colors
  const surfaces = [colors.field, colors.dugout, colors.chalk, colors.dirt]
  for (const token of ['chalk400', 'chalk500', 'chalk600']) {
    for (const surface of surfaces) {
      assert.ok(
        contrastRatio(colors[token], surface) >= 4.5,
        `${token} should pass AA on ${surface}`,
      )
    }
  }
})

test('semantic foundation colors remain readable with visible text on dark surfaces', () => {
  const colors = tailwindConfig.theme.extend.colors
  for (const token of [
    'stateFresh',
    'stateStretched',
    'stateVulnerable',
    'readAvailable',
    'readWatch',
    'readLimited',
    'readUnavailable',
    'signal',
    'gold',
  ]) {
    for (const surface of [colors.field, colors.dugout]) {
      assert.ok(
        contrastRatio(colors[token], surface) >= 4.5,
        `${token} should pass AA on ${surface}`,
      )
    }
  }
})

test('final Team Board text tones pass AA on every permitted surface', () => {
  const colors = tailwindConfig.theme.extend.colors
  const surfaces = ['surface-base', 'surface-nav', 'surface-raised', 'surface-hover']
  for (const token of ['text-primary', 'text-secondary', 'text-tertiary', 'text-withheld']) {
    for (const surface of surfaces) {
      assert.ok(
        contrastRatio(colors[token], colors[surface]) >= 4.5,
        `${token} should pass AA on ${surface}`,
      )
    }
  }
})

test('final Team Board focus, chart, semantic, and brand tokens meet contrast requirements', () => {
  const colors = tailwindConfig.theme.extend.colors
  const surfaces = ['surface-base', 'surface-nav', 'surface-raised', 'surface-hover']
  for (const surface of surfaces) {
    assert.ok(contrastRatio(colors['line-focus'], colors[surface]) >= 3, `line-focus on ${surface}`)
  }
  assert.ok(contrastRatio(colors['chart-bar'], colors['surface-base']) >= 3)

  for (const token of ['state-clear', 'state-caution', 'state-constrained']) {
    assert.ok(contrastRatio(colors[token], colors['surface-base']) >= 4.5, `${token} on surface-base`)
    const tint = blendHex(colors[token], colors['surface-base'], 0.1)
    assert.ok(contrastRatio(colors[token], tint) >= 4.5, `${token} on its 10% tint`)
  }

  for (const token of ['brand-blue', 'brand-gold']) {
    assert.ok(contrastRatio(colors[token], colors['surface-base']) >= 4.5, `${token} on surface-base`)
  }
  assert.ok(contrastRatio(colors['text-secondary'], colors['text-withheld']) >= 1.5)
  assert.equal(new Set(surfaces.map(token => colors[token])).size, surfaces.length)
})
