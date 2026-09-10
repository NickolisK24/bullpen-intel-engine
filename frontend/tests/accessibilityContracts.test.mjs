import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const read = relative => readFileSync(new URL(relative, import.meta.url), 'utf8')

function luminance(hex) {
  const channels = hex.match(/[a-f\d]{2}/gi).map(value => parseInt(value, 16) / 255)
  const linear = channels.map(value => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4)
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
}

function contrast(foreground, background) {
  const values = [luminance(foreground), luminance(background)].sort((a, b) => b - a)
  return (values[0] + 0.05) / (values[1] + 0.05)
}

test('shell owns a first-class skip target and path-only route focus policy', () => {
  const app = read('../src/App.jsx')
  const routeAccessibility = read('../src/components/RouteAccessibility.jsx')
  assert.match(app, /Skip to main content/)
  assert.match(app, /id="main-content" tabIndex=\{-1\}/)
  assert.match(routeAccessibility, /previousPath\.current === location\.pathname/)
  assert.match(routeAccessibility, /querySelector\('h1'\)/)
  assert.match(routeAccessibility, /aria-live="polite"/)
})

test('crash fallback uses high-contrast tokens, alert semantics, focus, and a native recovery button', () => {
  const source = read('../src/components/AppErrorBoundary.jsx')
  assert.match(source, /role="alert"/)
  assert.match(source, /errorRef\.current\?\.focus\(\)/)
  assert.match(source, /text-chalk100/)
  assert.match(source, /text-chalk300/)
  assert.doesNotMatch(source, /text-chalk\/55|text-chalk\/70|text-chalk sm:/)
  assert.match(source, /<button[\s\S]*Reload[\s\S]*<\/button>/)
})

test('Finder keeps native table and link semantics', () => {
  const source = read('../src/components/bullpen/Bullpen.jsx')
  assert.match(source, /<th scope="col" aria-sort=/)
  assert.match(source, /<button[\s\S]*setSortBy\(column\)/)
  assert.match(source, /<Link[\s\S]*Open pitcher detail/)
  assert.doesNotMatch(source, /role: 'button'/)
  assert.doesNotMatch(source, /<tr[\s\S]{0,180}onClick=/)
})

test('share interactions use disclosure buttons and evidence uses native name-value semantics', () => {
  const menu = read('../src/components/share/EvidenceShareMenu.jsx')
  const card = read('../src/components/share/TeamStateArtifactCard.jsx')
  assert.doesNotMatch(menu, /role="menu"|role="menuitem"|aria-haspopup="menu"/)
  assert.match(menu, /aria-expanded=\{open\}/)
  assert.match(menu, /event\.key === 'Escape'/)
  assert.doesNotMatch(card, /role="table"|role="row"|role="columnheader"/)
  assert.match(card, /<dl/)
  assert.match(card, /<dt/)
  assert.match(card, /<dd/)
})

test('metadata and crash text tokens clear WCAG AA normal-text contrast', () => {
  assert.ok(contrast('#D8B568', '#0F1620') >= 4.5)
  assert.ok(contrast('#F2F4F1', '#0F1620') >= 4.5)
  assert.ok(contrast('#BCC8D3', '#0F1620') >= 4.5)
})

test('global reduced-motion policy covers animations, transitions, and smooth scrolling', () => {
  const css = read('../src/index.css')
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/)
  assert.match(css, /animation-duration: 0\.01ms !important/)
  assert.match(css, /transition-duration: 0\.01ms !important/)
  assert.match(css, /scroll-behavior: auto !important/)
})
