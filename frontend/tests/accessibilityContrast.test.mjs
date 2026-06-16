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
