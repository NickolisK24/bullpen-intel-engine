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

// The product experience surfaces (ink / panel / panel-2) carry the same muted
// text tokens plus the blue and gold accents. Accents are used for real labels,
// not decoration, so they are held to the same AA threshold as body text.
test('product experience text and accent tokens meet WCAG AA on every panel surface', () => {
  const colors = tailwindConfig.theme.extend.colors
  const surfaces = [colors.ink, colors.panel, colors['panel-2']]
  const foregrounds = [
    'chalk100', 'chalk200', 'chalk300', 'chalk400', 'chalk500', 'chalk600',
    'signal', 'signal-deep', 'brass', 'brass-deep', 'focus',
  ]
  for (const token of foregrounds) {
    for (const surface of surfaces) {
      assert.ok(
        contrastRatio(colors[token], surface) >= 4.5,
        `${token} should pass AA on ${surface}`,
      )
    }
  }
})
