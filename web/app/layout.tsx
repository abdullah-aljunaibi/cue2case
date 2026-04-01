// Root HTML shell for the minimal Cue2Case Next.js app.
import type { ReactNode } from 'react';

export const metadata = {
  title: 'Cue2Case',
  description: 'Case-first maritime anomaly triage',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
