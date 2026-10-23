# Офис портал

Уеб файлов мениджър за офис сървъра (FastAPI + SQLite). Потребителите и папките се правят от портала, не са зададени в кода.

## Пускане (разработка)
    py -3.11 -m venv .venv
    .venv\Scripts\pip install -r requirements.txt
    copy .env.example .env      (сменете DATA_ROOT)
    .venv\Scripts\python -m app.cli create-admin admin
    .venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000

## Тестове
    .venv\Scripts\python -m pytest

## Бележки
- Паролата на админа се показва само веднъж.
- COOKIE_SECURE=1 щом портала е зад HTTPS (Caddy).
- Лимитът на опитите за вход е в паметта и се нулира при рестарт.
