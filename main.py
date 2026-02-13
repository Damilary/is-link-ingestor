from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import os
import json
import csv
import io

APP_NAME = "InsideSuccess Link Ingestor"
MAX_STORED_INGESTS = int(os.getenv("MAX_STORED_INGESTS", "50"))

# Optional security: set this in Cloud Run env vars.
# If set, POST requests to /ingest must send header x-api-key: <value>
API_KEY = os.getenv("API_KEY", "").strip()

app = FastAPI(title=APP_NAME)

# ---- Models ----
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

# ---- In-memory store (Cloud Run instance memory; good for UI + quick checks) ----
INGEST_STORE: List[Dict[str, Any]] = []

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def require_api_key(request: Request):
    if not API_KEY:
        return  # security disabled
    provided = request.headers.get("x-api-key", "")
    if provided != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized: missing/invalid x-api-key")

def add_ingest(record: Dict[str, Any]):
    INGEST_STORE.insert(0, record)
    if len(INGEST_STORE) > MAX_STORED_INGESTS:
        del INGEST_STORE[MAX_STORED_INGESTS:]

def render_ui() -> str:
    rows = []
    for idx, rec in enumerate(INGEST_STORE[:20], start=1):
        rows.append(f"""
          <tr>
            <td>{idx}</td>
            <td>{rec.get("received_at","")}</td>
            <td>{rec.get("platform","")}</td>
            <td>{rec.get("source","")}</td>
            <td>{rec.get("count",0)}</td>
            <td style="max-width:420px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">{rec.get("page","")}</td>
          </tr>
        """)

    table = """
      <p style="opacity:.8;">No ingests received yet. Use OrangeMonkey “POST to CR” or upload a JSON payload below.</p>
    """ if not rows else f"""
      <table>
        <thead>
          <tr>
            <th>#</th><th>Received</th><th>Platform</th><th>Source</th><th>Count</th><th>Page</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows)}
        </tbody>
      </table>
      <div class="row" style="margin-top:12px;">
        <a class="btn" href="/download/latest.csv">Download latest CSV</a>
        <a class="btn secondary" href="/api/ingests">View /api/ingests</a>
      </div>
    """

    return f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>{APP_NAME}</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; background:#0b0b0c; color:#f2f2f2; margin:0; }}
    .wrap {{ max-width: 980px; margin: 0 auto; padding: 28px 18px; }}
    .card {{ background:#141416; border:1px solid #26262a; border-radius:16px; padding:16px; margin:14px 0; }}
    h1 {{ font-size:20px; margin:0 0 6px 0; }}
    p {{ margin:8px 0; line-height:1.45; }}
    input, textarea, select {{ width:100%; padding:10px; border-radius:12px; border:1px solid #2b2b2f; background:#0f0f11; color:#fff; }}
    textarea {{ min-height:110px; }}
    .row {{ display:flex; gap:12px; flex-wrap:wrap; }}
    .row > div {{ flex:1; min-width: 220px; }}
    .btn {{ display:inline-block; padding:10px 12px; border-radius:12px; border:0; background:#ffffff; color:#000; text-decoration:none; cursor:pointer; font-weight:600; }}
    .btn.secondary {{ background:#2a2a2f; color:#fff; }}
    table {{ width:100%; border-collapse:collapse; }}
    th, td {{ padding:10px; border-bottom:1px solid #242428; font-size:13px; text-align:left; }}
    th {{ opacity:.85; }}
    .small {{ font-size:12px; opacity:.8; }}
    .ok {{ color:#7CFF9B; }}
    .warn {{ color:#FFD37C; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>{APP_NAME}</h1>
      <p class="small">Service time (UTC): <span class="ok">{utc_now_iso()}</span></p>
      <p class="small">Stored ingests in this instance: <b>{len(INGEST_STORE)}</b> (max {MAX_STORED_INGESTS}).</p>
      <p class="small warn">Note: Cloud Run memory is not permanent. If you want persistence, next upgrade is Firestore/BigQuery.</p>
    </div>

    <div class="card">
      <h1>Recent ingests</h1>
      {table}
    </div>

    <div class="card">
      <h1>Upload OM JSON payload</h1>
      <form method="post" action="/ui/upload" enctype="multipart/form-data">
        <input type="file" name="file" accept=".json,application/json" required />
        <div class="row" style="margin-top:12px;">
          <button class="btn" type="submit">Upload & Save</button>
          <a class="btn secondary" href="/">Refresh</a>
        </div>
      </form>
      <p class="small">This expects the same JSON structure OM exports via “Export JSON”.</p>
    </div>

    <div class="card">
      <h1>Paste links manually</h1>
      <form method="post" action="/ui/paste">
        <div class="row">
          <div>
            <label class="small">Platform</label>
            <select name="platform">
              <option value="x">x</option>
              <option value="instagram">instagram</option>
              <option value="facebook">facebook</option>
              <option value="tiktok">tiktok</option>
            </select>
          </div>
          <div>
            <label class="small">Date (optional ISO)</label>
            <input name="dateISO" placeholder="2026-02-13T12:00:00Z"/>
          </div>
        </div>
        <div style="margin-top:12px;">
          <label class="small">One URL per line</label>
          <textarea name="links" placeholder="https://x.com/.../status/...\nhttps://www.instagram.com/p/..."></textarea>
        </div>
        <div class="row" style="margin-top:12px;">
          <button class="btn" type="submit">Save Links</button>
          <a class="btn secondary" href="/download/latest.csv">Download latest CSV</a>
        </div>
      </form>
    </div>

  </div>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def ui_home():
    return render_ui()

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/api/ingests")
def api_ingests():
    return {"count": len(INGEST_STORE), "items": INGEST_STORE}

@app.post("/ingest")
async def ingest(payload: Payload, request: Request):
    require_api_key(request)

    record = {
        "received_at": utc_now_iso(),
        "source": payload.source,
        "page": payload.page,
        "platform": payload.platform,
        "startDate": payload.startDate,
        "endDate": payload.endDate,
        "count": len(payload.items),
        "items": [i.model_dump() for i in payload.items],
        "client": request.client.host if request.client else None,
    }
    add_ingest(record)

    print({"event": "ingest", "platform": payload.platform, "count": len(payload.items), "received_at": record["received_at"]})
    return {"status": "ok", "count": len(payload.items)}

@app.post("/ui/upload", response_class=HTMLResponse)
async def ui_upload(file: UploadFile = File(...)):
    raw = await file.read()
    data = json.loads(raw.decode("utf-8", errors="ignore"))

    # Accept OM export JSON too
    if "items" in data and isinstance(data["items"], list) and "platform" in data:
        # Looks like an ingest payload already
        record = {
            "received_at": utc_now_iso(),
            "source": data.get("source", "upload"),
            "page": data.get("page", ""),
            "platform": data.get("platform", "unknown"),
            "startDate": data.get("startDate", ""),
            "endDate": data.get("endDate", ""),
            "count": len(data["items"]),
            "items": data["items"],
            "client": "upload",
        }
    else:
        # Might be OM "export JSON" format:
        # { exportedAt, page, startDate, endDate, count, items:[{platform,dateISO,url,text}] }
        items = data.get("items", [])
        platform = "unknown"
        if items and isinstance(items, list) and isinstance(items[0], dict):
            platform = items[0].get("platform", "unknown")
        record = {
            "received_at": utc_now_iso(),
            "source": "upload",
            "page": data.get("page", ""),
            "platform": platform,
            "startDate": data.get("startDate", ""),
            "endDate": data.get("endDate", ""),
            "count": len(items),
            "items": items,
            "client": "upload",
        }

    add_ingest(record)
    return render_ui()

@app.post("/ui/paste", response_class=HTMLResponse)
async def ui_paste(
    platform: str = Form("unknown"),
    dateISO: str = Form(""),
    links: str = Form("")
):
    urls = [ln.strip() for ln in links.splitlines() if ln.strip()]
    items = [{"platform": platform, "dateISO": dateISO.strip() or "", "url": u, "text": ""} for u in urls]

    record = {
        "received_at": utc_now_iso(),
        "source": "manual",
        "page": "",
        "platform": platform,
        "startDate": "",
        "endDate": "",
        "count": len(items),
        "items": items,
        "client": "manual",
    }
    add_ingest(record)
    return render_ui()

@app.get("/download/latest.csv")
def download_latest_csv():
    if not INGEST_STORE:
        return PlainTextResponse("No ingests stored yet.", status_code=404)

    rec = INGEST_STORE[0]
    items = rec.get("items", [])

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["platform", "dateISO", "url", "text"])
    for it in items:
        writer.writerow([it.get("platform",""), it.get("dateISO",""), it.get("url",""), (it.get("text","") or "")[:240]])

    csv_bytes = output.getvalue().encode("utf-8")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=latest.csv"}
    )
