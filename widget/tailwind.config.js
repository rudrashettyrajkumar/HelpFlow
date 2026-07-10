import typography from '@tailwindcss/typography'

/** Semantic tokens resolve to CSS variables (see src/index.css) so a single
 *  `data-theme` attribute on <html> flips the whole palette — the widget
 *  picks its OWN theme from the embed.js `?theme=` query param rather than
 *  inheriting `.dark` from a host page (the iframe is a separate document;
 *  there is nothing to inherit — host-CSS isolation, spec Req 8). */
const withAlpha = (v) => `rgb(var(${v}) / <alpha-value>)`

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['selector', '[data-theme="dark"]'],
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
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
        bubble: '0 10px 30px -8px rgb(var(--brand) / 0.5)',
      },
      backgroundImage: {
        'brand-gradient': 'linear-gradient(135deg, rgb(var(--brand)), rgb(var(--brand-2)))',
      },
      keyframes: {
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'pop-in': {
          '0%': { opacity: '0', transform: 'scale(0.9) translateY(8px)' },
          '100%': { opacity: '1', transform: 'scale(1) translateY(0)' },
        },
        blink: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.2' },
        },
      },
      animation: {
        'fade-up': 'fade-up 0.35s cubic-bezier(0.16,1,0.3,1) both',
        'fade-in': 'fade-in 0.25s ease-out both',
        'pop-in': 'pop-in 0.3s cubic-bezier(0.16,1,0.3,1) both',
        blink: 'blink 1s step-end infinite',
      },
    },
  },
  plugins: [typography],
}
