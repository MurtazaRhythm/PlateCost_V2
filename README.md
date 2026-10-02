# PlateCost

Restaurant bookkeeping. Photograph a receipt in a few sections, and PlateCost reads it with Gemini and files the expense in Supabase.

One physical receipt is one `receipt_session`. Every photo on that receipt shares the session and keeps its top-to-bottom `sequence_number`. The phone and the future receipt device both send images into the same session API.

## Mobile app

```powershell
.\.venv\Scripts\python -m pip install -r requirements.txt
npm install --prefix web
copy .env.example .env   # fill in Gemini and Supabase keys
```

Run `supabase/schema.sql` once in the Supabase SQL editor, then `supabase/migrations/20261002_receipt_sessions.sql` if the project was created before receipt sessions existed.

Start the API and the app in two terminals:

```powershell
.\.venv\Scripts\python -m uvicorn server.main:app --host 127.0.0.1 --port 8000
npm run dev --prefix web
```

If port 8000 is already taken, start the API on another port and set `API_PROXY_TARGET=http://127.0.0.1:8010` in `web/.env.local`.

Open http://localhost:3000 on your phone or computer, create an account, and tap **Capture Receipt**. The browser camera is used when the page is a secure context (localhost or HTTPS). Otherwise **Capture** opens the phone's camera directly.

`POST /api/receipt-sessions/{session_id}/process` loads that session's images in sequence order, sends them to Gemini as one receipt, and stores the result. Gemini and the Supabase service role stay on the server.

## Folder pipeline

The original folder workflow still uses the same extraction code:

```powershell
.\.venv\Scripts\python process_receipts.py
.\.venv\Scripts\python process_receipts.py --folder ROne
.\.venv\Scripts\python process_receipts.py --dry-run
```

Each subfolder of `Receipt demos` is one receipt, with photos in top-to-bottom filename order.
