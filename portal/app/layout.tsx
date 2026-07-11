import type { Metadata } from 'next'
import { AuthProvider } from '@/lib/auth-context'
import { THEME_ANTI_FLASH_SCRIPT, ThemeProvider } from '@/lib/theme'
import './globals.css'

export const metadata: Metadata = {
  title: 'HelpFlow — an AI support agent that knows when to get a human',
  description:
    'Paste your site, watch it learn, and get a grounded, cited chat widget in minutes — with a real human handoff when the AI genuinely doesn\'t know. Free demo mode, bring-your-own-key for full control.',
  openGraph: {
    title: 'HelpFlow — an AI support agent that knows when to get a human',
    description:
      'Self-serve RAG support widget: crawl your site, chat with cited answers, hand off to a human when it matters.',
    type: 'website',
  },
  icons: { icon: '/favicon.svg' },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* eslint-disable-next-line react/no-danger */}
        <script dangerouslySetInnerHTML={{ __html: THEME_ANTI_FLASH_SCRIPT }} />
      </head>
      <body>
        <ThemeProvider>
          <AuthProvider>{children}</AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}
