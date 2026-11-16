<div align="center">
<img width="1200" height="475" alt="GHBanner" src="https://ai.google.dev/static/site-assets/images/share-ais-513315318.png" />
</div>

# Run and deploy your AI Studio app

This contains everything you need to run your app locally.

View your app in AI Studio: https://ai.studio/apps/1be7124c-5421-44e8-8f30-7bc5d60594d8

## Run Locally

**Prerequisites:** Node.js 24 recommended.


1. Install dependencies:
   `npm ci`
2. Run the app:
   `npm run dev -- --host 127.0.0.1 --port 5173`

By default the UI connects to the existing FastAPI backend at `http://127.0.0.1:8000`. Set `VITE_API_BASE` in `.env.local` to use a different URL. To restore the original mock UI without a backend, set `VITE_DEMO_MODE=true` and restart Vite. No frontend Gemini key is needed.
