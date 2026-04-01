// Placeholder landing page for the initial Cue2Case web scaffold.
const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function Page() {
  return (
    <main style={{ fontFamily: 'Arial, sans-serif', padding: '2rem' }}>
      <h1 style={{ marginBottom: '0.5rem' }}>Cue2Case</h1>
      <p style={{ marginTop: 0, marginBottom: '1rem' }}>
        Case-first maritime anomaly triage
      </p>
      <small>API URL: {apiUrl}</small>
    </main>
  );
}
