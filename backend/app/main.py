from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import accounts, auth, categories, dashboard, imports, institutions, recurring, rules, transactions
from app.core.config import get_settings


settings = get_settings()
app = FastAPI(title="Personal Finance Manager API", version="0.1.0", root_path=settings.api_root_path)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for api_router in (
    auth.router,
    institutions.router,
    accounts.router,
    imports.router,
    transactions.router,
    categories.router,
    rules.router,
    recurring.router,
    dashboard.router,
):
    app.include_router(api_router)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name}
