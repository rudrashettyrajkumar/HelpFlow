import type { Config } from 'tailwindcss'

// Same semantic-token approach as widget/tailwind.config.js (DocChat v2
// family look, ARCHITECTURE §8) — CSS vars so `.dark` flips the whole
// palette; `<alpha-value>` keeps opacity modifiers (bg-brand/10) working.
const withAlpha = (v: string) => `rgb(var(${v}) / <alpha-value>)`

const config: Config = {
  darkMode: 'class',
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}', './lib/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        background: withAlpha('--bg'),
        surface: withAlpha('--surface'),
        'surface-muted': withAlpha('--surface-muted'),
        border: withAlpha('--border'),
        foreground: withAlpha('--foreground'),
        'foreground-muted': withAlpha('--foreground-muted'),
        brand: withAlpha('--brand'),
        'brand-2': withAlpha('--brand-2'),
        accent: withAlpha('--accent'),
        success: withAlpha('--success'),
        destructive: withAlpha('--destructive'),
        ring: withAlpha('--ring'),
      },
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        xl: '0.875rem',
        '2xl': '1.125rem',
        '3xl': '1.75rem',
      },
      boxShadow: {
        glow: '0 0 0 1px rgb(var(--brand) / 0.15), 0 12px 40px -12px rgb(var(--brand) / 0.45)',
        'glow-accent': '0 12px 40px -12px rgb(var(--accent) / 0.55)',
        soft: '0 4px 24px -8px rgb(2 6 23 / 0.12)',
      },
      backgroundImage: {
        'brand-gradient': 'linear-gradient(135deg, rgb(var(--brand)), rgb(var(--brand-2)))',
      },
      keyframes: {
        float: {
          '0%, 100%': { transform: 'translate3d(0,0,0) scale(1)' },
          '33%': { transform: 'translate3d(3%, -4%, 0) scale(1.08)' },
          '66%': { transform: 'translate3d(-3%, 3%, 0) scale(0.96)' },
        },
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
      },
      animation: {
        float: 'float 18s ease-in-out infinite',
        'float-slow': 'float 26s ease-in-out infinite',
        'fade-up': 'fade-up 0.5s cubic-bezier(0.16,1,0.3,1) both',
        'fade-in': 'fade-in 0.4s ease-out both',
      },
    },
  },
  plugins: [],
}

export default config
