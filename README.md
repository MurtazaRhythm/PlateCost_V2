# PlateCost_V2

Reads photographed receipts with Gemini and stores the vendor, date, line items, taxes and totals in Supabase.

## Layout

```
process_receipts.py     Command-line entry point
receipts/
  models.py             Receipt schema, date and totals checks
  extract.py            Image prep and Gemini extraction
  store.py              Supabase Storage upload and database save
supabase/schema.sql     Tables and storage bucket (run once in the SQL editor)
scripts/
  organize_receipts.ps1 One-off: de-duplicate and rename photos in a folder
Receipt demos/          One subfolder per receipt, photos in top-to-bottom order (not committed)
```

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env   # then fill in the values
```

Run `supabase/schema.sql` once in the Supabase SQL editor.

## Usage

```powershell
.\.venv\Scripts\python process_receipts.py                 # all receipt folders
.\.venv\Scripts\python process_receipts.py --folder ROne   # one folder
.\.venv\Scripts\python process_receipts.py --dry-run       # print results, save nothing
```

Re-running updates existing receipts rather than duplicating them. Errors, warnings and timings go to Sentry Spotlight when it is running locally.
