// BaseballOS frontend foundation tokens.
//
// Tailwind consumes this module directly, making it the single value authority
// for color, type, spacing, breakpoints, and shell width. Components consume
// the named utilities Tailwind generates rather than copying raw values.
export const designTokens = Object.freeze({
  colors: Object.freeze({
    field: '#080d14',
    dugout: '#0f1620',
    chalk: '#18222e',
    dirt: '#26313e',
    signal: '#6e9fc8',
    gold: '#c89b4b',
    // Compatibility alias for existing surfaces. New foundation work uses
    // `gold` or `signal` according to purpose.
    amber: '#c89b4b',
    pine: '#4f8f70',
    warning: '#c38a3f',
    danger: '#bd6468',
    ice: '#8db9dc',
    stateFresh: '#79b99a',
    stateStretched: '#d5a45b',
    stateVulnerable: '#d77b7d',
    readAvailable: '#79b99a',
    readWatch: '#d5a45b',
    readLimited: '#d28b5d',
    readUnavailable: '#d77b7d',
    chalk100: '#f2f4f1',
    chalk200: '#d8dfe5',
    chalk300: '#bcc8d3',
    chalk400: '#a1afbe',
    chalk500: '#95a5b7',
    chalk600: '#899bad',
    chalk700: '#8294aa',
  }),
  typography: Object.freeze({
    'page-title': ['clamp(2rem, 4vw, 3.25rem)', { lineHeight: '0.96', letterSpacing: '0.025em' }],
    'section-title': ['1.5rem', { lineHeight: '1.1', letterSpacing: '0.025em' }],
    body: ['0.9375rem', { lineHeight: '1.55' }],
    compact: ['0.8125rem', { lineHeight: '1.45' }],
    metadata: ['0.75rem', { lineHeight: '1.35' }],
    overline: ['0.6875rem', { lineHeight: '1.2', letterSpacing: '0.12em' }],
    data: ['0.875rem', { lineHeight: '1.25' }],
  }),
  spacing: Object.freeze({
    meta: '0.375rem',
    row: '0.75rem',
    panel: '1rem',
    pair: '1rem',
    section: '1.5rem',
    'section-lg': '2rem',
  }),
  screens: Object.freeze({
    phone: '390px',
    tablet: '768px',
    desktop: '1280px',
    wide: '1440px',
  }),
  maxWidth: Object.freeze({
    reading: '72rem',
    'team-board': '90rem',
  }),
})
