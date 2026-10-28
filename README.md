# Dev Setup Assistant

A local developer setup assistant with login, signup, installation guides, operating-system profiles, image uploads, and an AI chat workspace.

## Run locally

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000/login`.

## Environment variables

Copy `.env.example` to `.env` and provide valid Groq and Qdrant credentials.

Never commit `.env`, `users.db`, API keys, or passwords.
