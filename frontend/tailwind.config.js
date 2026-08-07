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
        ink:            '#070a0d',   // Page ground, deeper than a panel
        panel:          '#0f1319',   // Primary panel surface
        'panel-2':      '#151a21',   // Inset / secondary panel surface
        line:           '#1e2530',   // Subtle hairline border
        'line-strong':  '#2c3644',   // Emphasized border
        signal:         '#8fb8e8',   // BaseballOS blue — labels, links, marks
        'signal-deep':  '#7aa9e0',   // Blue interaction / hover state
        'signal-well':  '#122234',   // Blue-tinted well behind a blue mark
        brass:          '#d8bd7e',   // Muted gold — editorial accent
        'brass-deep':   '#c9a961',   // Muted gold, pressed/secondary
        focus:          '#9ecbff',   // Focus ring

        // Core palette
        field:   '#0a0c0f',   // Near-black background
        dugout:  '#111418',   // Card/panel background
        chalk:   '#1a1f26',   // Elevated surface
        dirt:    '#242b35',   // Border/divider
        // Accents
        amber:   '#f5a623',   // Primary accent — stadium lights
        gold:    '#e8943a',   // Secondary warm accent
        pine:    '#2d6a4f',   // Green — safe/low fatigue
        warning: '#d97706',   // Amber — moderate fatigue
        danger:  '#dc2626',   // Red — high/critical fatigue
        ice:     '#93c5fd',   // Blue — cool stat highlight
        // Text
        chalk100: '#f0f4f8',
        chalk200: '#d1dce8',
        chalk300: '#b7c4d1',
        chalk400: '#9aa8b8',
        chalk500: '#8b9bae',
        chalk600: '#8294aa',
        chalk700: '#8294aa',
      },
      fontFamily: {
        display: ['"Bebas Neue"', 'sans-serif'],
        mono:    ['"JetBrains Mono"', 'monospace'],
        body:    ['"DM Sans"', 'sans-serif'],
      },
      // Deliberate rhythm steps for dense metadata, evidence rows, and the
      // section spacing the Today edition uses. Named rather than numeric so a
      // section's spacing intent survives refactors.
      spacing: {
        'gutter':      '1rem',
        'gutter-md':   '1.5rem',
        'gutter-lg':   '2rem',
        'rhythm-tight': '0.75rem',
        'rhythm':       '1.25rem',
        'rhythm-loose': '2.5rem',
        'section':      '3.5rem',
      },
      borderRadius: {
        // Restrained: panels stay rectilinear, only controls soften slightly.
        edge: '2px',
        panel: '4px',
        control: '6px',
      },
      boxShadow: {
        // Borders do the structural work; shadows only lift the signature
        // edition object off the page ground.
        panel: '0 1px 0 rgba(255,255,255,0.02), 0 18px 40px -34px rgba(0,0,0,0.95)',
        edition: '0 1px 0 rgba(255,255,255,0.03), 0 30px 70px -50px rgba(0,0,0,1)',
      },
      screens: {
        xs: '390px',
      },
      maxWidth: {
        measure: '68ch',
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
