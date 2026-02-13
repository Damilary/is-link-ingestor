from fastapi import FastAPI, Request
from pydantic import BaseModel, HttpUrl
from typing import List, Optional
from datetime import datetime

app = FastAPI(title="InsideSuccess Link Ingestor")

class Item(BaseModel):
    platform: str
    dateISO: Optional[str] = None
    url: HttpUrl
    text: Optional[str] = None

class Payload(BaseModel):
    source: str
    page: str
    platform: str
    startDate: str
    endDate: str
    items: List[Item]

@app.get("/")
def root():
    return {"status": "running"}

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/ingest")
async def ingest(payload: Payload, request: Request):
    count = len(payload.items)
    print({
        "event": "ingest",
        "platform": payload.platform,
        "count": count,
        "received_at": datetime.utcnow().isoformat() + "Z"
    })

    return {
        "status": "ok",
        "count": count
    }