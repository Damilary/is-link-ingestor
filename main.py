from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, PlainTextResponse, Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Dict, Any
from datetime import datetime
import io
import csv
import json

app = FastAPI(title="InsideSuccess Link Ingestor")

# ✅ CORS FIX: allow OrangeMonkey (running in browser) to POST to Cloud Run
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # later: restrict to specific origins if needed
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------- In-memory store (note: not persistent) --------
MAX_INGESTS = 50
INGESTS: List[Dict[str, Any]] = []  # each item: {received_at, platform, source, page, startDate, endDate, count, items}


class Item(BaseModel):
    platform: str
    dateISO: Optional[str] = None
    url: HttpUrl
    text: Optional[str] = None  # preview/caption line


class Payload(BaseModel):
    source: str
    page: str
    platform: str
    startDate: str
    endDate: str
    items: List[Item]


def now_utc_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def push_ingest(record: Dict[str, Any]) -> None:
    INGESTS.insert(0, record)
    if len(INGESTS) > MAX_INGESTS:
        del INGESTS[MAX_INGESTS:]


def latest_items_flat() -> List[Dict[str, Any]]:
    # flatten most recent ingest items
    if not INGESTS:
        return []
    return INGESTS[0].get("items", [])


def csv_from_items(items: List[Dict[str, Any]]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["platform", "dateISO", "url", "text"])
    for it in items:
        writer.writerow([
            it.get("platform", ""),
            it.get("dateISO", ""),
            it.get("url", ""),
            (it.get("text", "") or "").replace("\n", " ").strip()
        ])
    return output.getvalue()


@app.get("/", response_class=HTMLResponse)
def home():
    service_time = now_utc_iso()
    recent = INGESTS[:10]

    rows_html = ""
    if not recent:
        rows_html = "<div style='opacity:.8'>No ingests received yet. Use OrangeMonkey “POST” to CR or upload a JSON payload below.</div>"
    else:
        rows = []
        for i, r in enumerate(recent, start=1):
            rows.append(f"""
              <tr>
                <td style="padding:10px;border-bottom:1px solid #333">{i}</td>
                <td style="padding:10px;border-bottom:1px solid #333">{r.get("received_at","")}</td>
                <td style="padding:10px;border-bottom:1px solid #333">{r.get("platform","")}</td>
                <td style="padding:10px;border-bottom:1px solid #333">{r.get("source","")}</td>
                <td style="padding:10px;border-bottom:1px solid #333">{r.get("count","")}</td>
                <td style="padding:10px;border-bottom:1px solid #333;max-width:380px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                  {r.get("page","")}
                </td>
              </tr>
            """)

        rows_html = f"""
          <table style="width:100%;border-collapse:collapse;font-size:13px;">
            <thead>
              <tr style="text-align:left;opacity:.9">
                <th style="padding:10px;border-bottom:1px solid #333">#</th>
                <th style="padding:10px;border-bottom:1px solid #333">Received</th>
                <th style="padding:10px;border-bottom:1px solid #333">Platform</th>
                <th style="padding:10px;border-bottom:1px solid #333">Source</th>
                <th style="padding:10px;border-bottom:1px solid #333">Count</th>
                <th style="padding:10px;border-bottom:1px solid #333">Page</th>
              </tr>
            </thead>
            <tbody>
              {''.join(rows)}
            </tbody>
          </table>
        """

    html = f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>InsideSuccess Link Ingestor</title>
  <style>
    body {{
      margin:0; padding:0;
      font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial;
      background:#0b0d10; color:#fff;
    }}
    .wrap {{ max-width: 920px; margin: 0 auto; padding: 28px 16px 60px; }}
    .card {{
      background: rgba(255,255,255,0.04);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 14px;
      padding: 18px;
      margin-bottom: 14px;
      box-shadow: 0 14px 40px rgba(0,0,0,.25);
    }}
    .muted {{ opacity:.78; font-size:13px; }}
    .title {{ font-weight:900; font-size:18px; margin-bottom:6px; }}
    .btn {{
      display:inline-block;
      padding:10px 14px;
      border-radius:12px;
      border:0;
      background:#e7e7ea;
      color:#111;
      cursor:pointer;
      font-weight:650;
      text-decoration:none;
      margin-right:8px;
    }}
    .btn.secondary {{
      background: rgba(255,255,255,0.08);
      color:#fff;
      border:1px solid rgba(255,255,255,0.10);
    }}
    input, select, textarea {{
      width:100%;
      background: rgba(0,0,0,0.35);
      color:#fff;
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 12px;
      padding: 10px;
      outline:none;
      box-sizing: border-box;
    }}
    textarea {{ min-height: 110px; resize: vertical; }}
    label {{ font-size:12px; opacity:.8; display:block; margin-bottom:6px; }}
    .grid2 {{ display:grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
    .note {{ color:#ffd37c; font-size:12px; opacity:.9; margin-top:8px; }}
  </style>
</head>
<body>
  <div class="wrap">

    <div class="card">
      <div class="title">InsideSuccess Link Ingestor</div>
      <div class="muted">Service time (UTC): <b>{service_time}</b></div>
      <div class="muted" style="margin-top:6px;">Stored ingests in this instance: <b>{len(INGESTS)}</b> (max {MAX_INGESTS}).</div>
      <div class="note">Note: Cloud Run memory is not permanent. If you want persistence, next upgrade is Firestore/BigQuery.</div>
    </div>

    <div class="card">
      <div class="title">Recent ingests</div>
      {rows_html}
      <div style="margin-top:14px;">
        <a class="btn" href="/download/latest.csv">Download latest CSV</a>
        <a class="btn secondary" href="/api/ingests">View /api/ingests</a>
      </div>
    </div>

    <div class="card">
      <div class="title">Upload OM JSON payload</div>
      <form action="/upload" method="post" enctype="multipart/form-data">
        <input type="file" name="file" accept=".json,application/json" />
        <div style="margin-top:12px;">
          <button class="btn" type="submit">Upload &amp; Save</button>
          <a class="btn secondary" href="/">Refresh</a>
        </div>
      </form>
      <div class="muted" style="margin-top:10px;">This expects the same JSON structure OM exports via “Export JSON”.</div>
    </div>

    <div class="card">
      <div class="title">Paste links manually</div>
      <form action="/manual" method="post">
        <div class="grid2">
          <div>
            <label>Platform</label>
            <select name="platform">
              <option value="x">x</option>
              <option value="instagram">instagram</option>
              <option value="facebook">facebook</option>
              <option value="tiktok">tiktok</option>
            </select>
          </div>
          <div>
            <label>Date (optional ISO)</label>
            <input name="dateISO" placeholder="2026-02-13T12:00:00Z" />
          </div>
        </div>

        <div style="margin-top:12px;">
          <label>One URL per line</label>
          <textarea name="urls" placeholder="https://x.com/.../status/...
https://www.instagram.com/p/..."></textarea>
        </div>

        <div style="margin-top:12px;">
          <button class="btn" type="submit">Save Links</button>
          <a class="btn secondary" href="/download/latest.csv">Download latest CSV</a>
        </div>
      </form>
    </div>

  </div>
</body>
</html>
    """.strip()

    return HTMLResponse(content=html)


@app.get("/health")
def health():
    return {"ok": True}


# ✅ If user opens /ingest in browser, this explains what it’s for (prevents confusion)
@app.get("/ingest", response_class=PlainTextResponse)
def ingest_help():
    return PlainTextResponse(
        "This is the ingest API endpoint.\n\n"
        "Use POST /ingest with a JSON payload from OrangeMonkey.\n"
        "Open / (homepage) to see the UI dashboard.\n"
    )


@app.post("/ingest")
async def ingest(payload: Payload, request: Request):
    record = {
        "received_at": now_utc_iso(),
        "source": payload.source,
        "page": payload.page,
        "platform": payload.platform,
        "startDate": payload.startDate,
        "endDate": payload.endDate,
        "count": len(payload.items),
        "items": [it.model_dump() for it in payload.items],
        "client": request.client.host if request.client else None,
    }
    push_ingest(record)

    # Cloud Run logs
    print({
        "event": "ingest",
        "platform": payload.platform,
        "count": len(payload.items),
        "received_at": record["received_at"]
    })

    return {"status": "ok", "count": len(payload.items)}


@app.get("/api/ingests")
def api_ingests():
    return {"count": len(INGESTS), "max": MAX_INGESTS, "ingests": INGESTS}


@app.get("/download/latest.csv")
def download_latest_csv():
    items = latest_items_flat()
    csv_text = csv_from_items(items)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="latest.csv"'}
    )


@app.post("/upload")
async def upload_json(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return HTMLResponse("<h3>Invalid JSON file</h3><a href='/'>Back</a>", status_code=400)

    # Accept OM export JSON format:
    # { exportedAt, page, startDate, endDate, count, items: [...] }
    items = payload.get("items", [])
    platform = payload.get("platform", payload.get("sourcePlatform", "unknown"))
    page = payload.get("page", "uploaded-file")
    startDate = payload.get("startDate", "")
    endDate = payload.get("endDate", "")

    record = {
        "received_at": now_utc_iso(),
        "source": "upload",
        "page": page,
        "platform": platform if platform else "unknown",
        "startDate": startDate,
        "endDate": endDate,
        "count": len(items),
        "items": items,
        "client": None,
    }
    push_ingest(record)

    return HTMLResponse("<h3>Upload saved ✅</h3><a href='/'>Back to dashboard</a>")


@app.post("/manual")
async def manual_links(
    platform: str = Form(...),
    dateISO: str = Form(""),
    urls: str = Form(...)
):
    lines = [ln.strip() for ln in (urls or "").splitlines() if ln.strip()]
    items = [{"platform": platform, "dateISO": (dateISO or ""), "url": ln, "text": ""} for ln in lines]

    record = {
        "received_at": now_utc_iso(),
        "source": "manual",
        "page": "manual-input",
        "platform": platform,
        "startDate": "",
        "endDate": "",
        "count": len(items),
        "items": items,
        "client": None,
    }
    push_ingest(record)

    return HTMLResponse("<h3>Saved ✅</h3><a href='/'>Back to dashboard</a>")
