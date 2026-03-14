/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
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
        chalk400: '#8899aa',
        chalk600: '#4a5568',
      },
      fontFamily: {
        display: ['"Bebas Neue"', 'sans-serif'],
        mono:    ['"JetBrains Mono"', 'monospace'],
        body:    ['"DM Sans"', 'sans-serif'],
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
