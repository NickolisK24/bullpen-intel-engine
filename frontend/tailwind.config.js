/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // ── Product experience tokens ──────────────────────────────────────
        // The BaseballOS surface palette: a deep charcoal/navy foundation, a
        // restrained blue used for interaction and structure, and a muted gold
        // reserved for editorial marks. Every value below is validated against
        // the muted text tokens in tests/accessibilityContrast.test.mjs.
        ink:            '#0B0F14',   // Page ground
        panel:          '#10161E',   // Primary panel surface
        'panel-2':      '#141C26',   // Elevated / secondary panel surface
        'line-quiet':   '#171E27',   // Quiet dividers / table rails
        line:           '#232C38',   // Subtle hairline border
        'line-strong':  '#2E3A49',   // Emphasized border
        signal:         '#5B8CD6',   // BaseballOS blue — interaction and structure
        'signal-deep':  '#8FB2E0',   // Blue text / hover state
        'signal-well':  '#101B2A',   // Blue-tinted well behind a blue mark
        brass:          '#C9A96A',   // Muted gold — editorial accent
        'brass-deep':   '#A08D62',   // Evidence index / pressed accent
        focus:          '#5B8CD6',   // Focus ring

        // Core palette
        field:   '#0B0F14',   // Near-black background
        dugout:  '#10161E',   // Card/panel background
        chalk:   '#141C26',   // Elevated surface
        dirt:    '#232C38',   // Border/divider
        // Accents
        amber:   '#C9A96A',   // Restrained editorial accent
        gold:    '#C9A96A',   // Secondary warm accent
        pine:    '#6FB6A0',   // Fresh state hue
        warning: '#D6A45C',   // Stretched state hue
        danger:  '#C97F6E',   // Vulnerable state hue
        ice:     '#93c5fd',   // Blue — cool stat highlight
        // Text
        chalk100: '#E9EEF5',
        chalk200: '#B4C0CE',
        chalk300: '#A1ADBC',
        chalk400: '#96A3B4',
        chalk500: '#8592A3',
        chalk600: '#788698',
        chalk700: '#788698',
      },
      fontFamily: {
        display: ['"Archivo Narrow"', 'sans-serif'],
        mono:    ['"IBM Plex Mono"', 'monospace'],
        body:    ['"IBM Plex Sans"', 'sans-serif'],
      },
      // Deliberate rhythm steps for dense metadata, evidence rows, and the
      // section spacing the Today edition uses. Named rather than numeric so a
      // section's spacing intent survives refactors.
      spacing: {
        'gutter':      '1.5rem',
        'gutter-md':   '1.5rem',
        'gutter-lg':   '1.5rem',
        'rhythm-tight': '0.75rem',
        'rhythm':       '1.125rem',
        'rhythm-loose': '2.25rem',
        'section':      '2.75rem',
      },
      borderRadius: {
        // Restrained: panels stay rectilinear, only controls soften slightly.
        DEFAULT: '0',
        sm: '0',
        md: '0',
        lg: '0',
        xl: '0',
        '2xl': '0',
        '3xl': '0',
        edge: '0',
        panel: '0',
        control: '0',
      },
      boxShadow: {
        // Foundations uses surface contrast and hairlines, never shadow.
        panel: 'none',
        edition: 'none',
      },
      screens: {
        xs: '390px',
      },
      maxWidth: {
        shell: '85rem',
        reading: '72.5rem',
        measure: '66ch',
        definition: '76ch',
        lead: '24ch',
      },
      backgroundImage: {
        'grid-lines': `linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px),
                       linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px)`,
        'stadium-glow': 'radial-gradient(ellipse at 50% 0%, rgba(245,166,35,0.08) 0%, transparent 60%)',
      },
      backgroundSize: {
        'grid-lines': '40px 40px',
      },
      animation: {
        'fade-up':      'fadeUp 0.5s ease forwards',
        'fade-in':      'fadeIn 0.4s ease forwards',
        'pulse-amber':  'pulseAmber 2s ease-in-out infinite',
        'slide-right':  'slideRight 0.6s ease forwards',
        'count-up':     'countUp 0.8s ease forwards',
      },
      keyframes: {
        fadeUp:      { '0%': { opacity: 0, transform: 'translateY(16px)' }, '100%': { opacity: 1, transform: 'translateY(0)' } },
        fadeIn:      { '0%': { opacity: 0 }, '100%': { opacity: 1 } },
        pulseAmber:  { '0%,100%': { boxShadow: '0 0 0 0 rgba(245,166,35,0)' }, '50%': { boxShadow: '0 0 12px 2px rgba(245,166,35,0.25)' } },
        slideRight:  { '0%': { opacity: 0, transform: 'translateX(-20px)' }, '100%': { opacity: 1, transform: 'translateX(0)' } },
        countUp:     { '0%': { opacity: 0 }, '100%': { opacity: 1 } },
      },
    },
  },
  plugins: [],
}
