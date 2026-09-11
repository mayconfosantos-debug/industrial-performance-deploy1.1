# Industrial Performance API

Run locally:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The active workbook is persisted in `data/active_base.json` after a Data Lake publish action.
