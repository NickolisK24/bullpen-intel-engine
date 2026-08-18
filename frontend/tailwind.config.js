import { designTokens } from './src/styles/designTokens.js'

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: designTokens.colors,
      fontSize: designTokens.typography,
      spacing: designTokens.spacing,
      screens: designTokens.screens,
      maxWidth: designTokens.maxWidth,
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
        'slide-right':  'slideRight 0.6s ease forwards',
        'count-up':     'countUp 0.8s ease forwards',
      },
      keyframes: {
        fadeUp:      { '0%': { opacity: 0, transform: 'translateY(16px)' }, '100%': { opacity: 1, transform: 'translateY(0)' } },
        fadeIn:      { '0%': { opacity: 0 }, '100%': { opacity: 1 } },
        slideRight:  { '0%': { opacity: 0, transform: 'translateX(-20px)' }, '100%': { opacity: 1, transform: 'translateX(0)' } },
        countUp:     { '0%': { opacity: 0 }, '100%': { opacity: 1 } },
      },
    },
  },
  plugins: [],
}
