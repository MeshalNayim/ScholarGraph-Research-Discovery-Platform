## API service

Run locally (after bringing up Docker services and ingesting data):

```bash
source .venv/bin/activate
uvicorn apps.api.main:app --reload --port 8000
```

Endpoints correspond to the competency questions in `resources/Topic_Details.md` and include a `store_justification` field in responses.

