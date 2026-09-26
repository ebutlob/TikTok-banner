"""
TikTok Profile Bulk Reporter — single file.
Serves the UI + runs the reporting engine + signs requests (X-Bogus).
"""
import asyncio
import json
import os
import random
import secrets
import string
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# ------------------------------------------------------------------
# 1. SIGNER — writes a node script to /tmp at boot
# ------------------------------------------------------------------
XBOGUS_JS = r"""
const CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=';
function rc4(key, data) {
  let s = [], j = 0, x, res = '';
  for (let i = 0; i < 256; i++) s[i] = i;
  for (let i = 0; i < 256; i++) {
    j = (j + s[i] + key.charCodeAt(i % key.length)) % 256;
    x = s[i]; s[i] = s[j]; s[j] = x;
  }
  let i = 0; j = 0;
  for (let y = 0; y < data.length; y++) {
    i = (i + 1) % 256;
    j = (j + s[i]) % 256;
    x = s[i]; s[i] = s[j]; s[j] = x;
    res += String.fromCharCode(data.charCodeAt(y) ^ s[(s[i] + s[j]) % 256]);
  }
  return res;
}
function md5(input) {
  function rl(n, c) { return (n << c) | (n >>> (32 - c)); }
  function au(x, y) { const l = (x & 0xFFFF) + (y & 0xFFFF); return (((x >> 16) + (y >> 16) + (l >> 16)) << 16) | (l & 0xFFFF); }
  function cmn(q, a, b, x, s, t) { return au(rl(au(au(a, q), au(x, t)), s), b); }
  function ff(a, b, c, d, x, s, t) { return cmn((b & c) | (~b & d), a, b, x, s, t); }
  function gg(a, b, c, d, x, s, t) { return cmn((b & d) | (c & ~d), a, b, x, s, t); }
  function hh(a, b, c, d, x, s, t) { return cmn(b ^ c ^ d, a, b, x, s, t); }
  function ii(a, b, c, d, x, s, t) { return cmn(c ^ (b | ~d), a, b, x, s, t); }
  function tb(str) {
    const n = str.length, blks = [];
    for (let i = 0; i < n * 8; i += 8) blks[i >> 5] |= (str.charCodeAt(i / 8) & 0xFF) << (i % 32);
    return blks;
  }
  function utf8(s) { return unescape(encodeURIComponent(s)); }
  let x = tb(utf8(input));
  const len = utf8(input).length * 8;
  x[len >> 5] |= 0x80 << (len % 32);
  x[(((len + 64) >>> 9) << 4) + 14] = len;
  let a = 1732584193, b = -271733879, c = -1732584194, d = 271733878;
  for (let i = 0; i < x.length; i += 16) {
    const oa = a, ob = b, oc = c, od = d;
    a = ff(a, b, c, d, x[i + 0], 7, -680876936);
    d = ff(d, a, b, c, x[i + 1], 12, -389564586);
    c = ff(c, d, a, b, x[i + 2], 17, 606105819);
    b = ff(b, c, d, a, x[i + 3], 22, -1044525330);
    a = ff(a, b, c, d, x[i + 4], 7, -176418897);
    d = ff(d, a, b, c, x[i + 5], 12, 1200080426);
    c = ff(c, d, a, b, x[i + 6], 17, -1473231341);
    b = ff(b, c, d, a, x[i + 7], 22, -45705983);
    a = ff(a, b, c, d, x[i + 8], 7, 1770035416);
    d = ff(d, a, b, c, x[i + 9], 12, -1958414417);
    c = ff(c, d, a, b, x[i + 10], 17, -42063);
    b = ff(b, c, d, a, x[i + 11], 22, -1990404162);
    a = ff(a, b, c, d, x[i + 12], 7, 1804603682);
    d = ff(d, a, b, c, x[i + 13], 12, -40341101);
    c = ff(c, d, a, b, x[i + 14], 17, -1502002290);
    b = ff(b, c, d, a, x[i + 15], 22, 1236535329);
    a = gg(a, b, c, d, x[i + 1], 5, -165796510);
    d = gg(d, a, b, c, x[i + 6], 9, -1069501632);
    c = gg(c, d, a, b, x[i + 11], 14, 643717713);
    b = gg(b, c, d, a, x[i + 0], 20, -373897302);
    a = gg(a, b, c, d, x[i + 5], 5, -701558691);
    d = gg(d, a, b, c, x[i + 10], 9, 38016083);
    c = gg(c, d, a, b, x[i + 15], 14, -660478335);
    b = gg(b, c, d, a, x[i + 4], 20, -405537848);
    a = gg(a, b, c, d, x[i + 9], 5, 568446438);
    d = gg(d, a, b, c, x[i + 14], 9, -1019803690);
    c = gg(c, d, a, b, x[i + 3], 14, -187363961);
    b = gg(b, c, d, a, x[i + 8], 20, 1163531501);
    a = gg(a, b, c, d, x[i + 13], 5, -1444681467);
    d = gg(d, a, b, c, x[i + 2], 9, -51403784);
    c = gg(c, d, a, b, x[i + 7], 14, 1735328473);
    b = gg(b, c, d, a, x[i + 12], 20, -1926607734);
    a = hh(a, b, c, d, x[i + 5], 4, -378558);
    d = hh(d, a, b, c, x[i + 8], 11, -2022574463);
    c = hh(c, d, a, b, x[i + 11], 16, 1839030562);
    b = hh(b, c, d, a, x[i + 14], 23, -35309556);
    a = hh(a, b, c, d, x[i + 1], 4, -1530992060);
    d = hh(d, a, b, c, x[i + 4], 11, 1272893353);
    c = hh(c, d, a, b, x[i + 7], 16, -155497632);
    b = hh(b, c, d, a, x[i + 10], 23, -1094730640);
    a = hh(a, b, c, d, x[i + 13], 4, 681279174);
    d = hh(d, a, b, c, x[i + 0], 11, -358537222);
    c = hh(c, d, a, b, x[i + 3], 16, -722521979);
    b = hh(b, c, d, a, x[i + 6], 23, 76029189);
    a = hh(a, b, c, d, x[i + 9], 4, -640364487);
    d = hh(d, a, b, c, x[i + 12], 11, -421815835);
    c = hh(c, d, a, b, x[i + 15], 16, 530742520);
    b = hh(b, c, d, a, x[i + 2], 23, -995338651);
    a = ii(a, b, c, d, x[i + 0], 6, -198630844);
    d = ii(d, a, b, c, x[i + 7], 10, 1126891415);
    c = ii(c, d, a, b, x[i + 14], 15, -1416354905);
    b = ii(b, c, d, a, x[i + 5], 21, -57434055);
    a = ii(a, b, c, d, x[i + 12], 6, 1700485571);
    d = ii(d, a, b, c, x[i + 3], 10, -1894986606);
    c = ii(c, d, a, b, x[i + 10], 15, -1051523);
    b = ii(b, c, d, a, x[i + 1], 21, -2054922799);
    a = ii(a, b, c, d, x[i + 8], 6, 1873313359);
    d = ii(d, a, b, c, x[i + 15], 10, -30611744);
    c = ii(c, d, a, b, x[i + 6], 15, -1560198380);
    b = ii(b, c, d, a, x[i + 13], 21, 1309151649);
    a = ii(a, b, c, d, x[i + 4], 6, -145523070);
    d = ii(d, a, b, c, x[i + 11], 10, -1120210379);
    c = ii(c, d, a, b, x[i + 2], 15, 718787259);
    b = ii(b, c, d, a, x[i + 9], 21, -343485551);
    a = au(a, oa); b = au(b, ob); c = au(c, oc); d = au(d, od);
  }
  function hx(n) {
    let s = '';
    for (let i = 0; i < 4; i++) s += ('0' + ((n >> (i * 8)) & 0xFF).toString(16)).slice(-2);
    return s;
  }
  return (hx(a) + hx(b) + hx(c) + hx(d));
}
function signXbogus(params, ua) {
  const ts = Math.floor(Date.now() / 1000);
  const signInput = params + ua + ts;
  const m1 = md5(signInput);
  const m2 = md5(m1);
  const m3 = md5(m2 + params);
  const rc = rc4(m2, m3);
  let result = '';
  for (let i = 0; i < 32; i++) {
    const c = rc.charCodeAt(i);
    let x = (c ^ (i & 0xff)) & 0xff;
    result += CHARS[(x >> 2) & 0x3f] + CHARS[((x << 4) & 0x3f) ^ (i & 0x0f)];
  }
  return 'DFSzswVL' + result.slice(0, 24) + 'dH';
}
let buf = '';
process.stdin.on('data', d => buf += d.toString());
process.stdin.on('end', () => {
  try {
    const { url, user_agent } = JSON.parse(buf);
    const q = url.split('?')[1] || '';
    process.stdout.write(signXbogus(q, user_agent));
  } catch (e) { process.stderr.write(e.message); process.exit(1); }
});
"""

SIGNER_PATH = Path(tempfile.gettempdir()) / "xbogus_signer.js"
SIGNER_PATH.write_text(XBOGUS_JS)


async def sign_xbogus(url: str, ua: str) -> str:
    payload = json.dumps({"url": url, "user_agent": ua}).encode()
    proc = await asyncio.create_subprocess_exec(
        "node", str(SIGNER_PATH),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(payload), timeout=5)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("signer timeout")
    if proc.returncode != 0:
        raise RuntimeError(f"signer fail: {err.decode(errors='ignore')}")
    return out.decode().strip()


# ------------------------------------------------------------------
# 2. TIKTOK SESSION — bootstrap + signed requests
# ------------------------------------------------------------------
DESKTOP_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
MOBILE_UA = "Mozilla/5.0 (Linux; Android 13; SM-S901B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Mobile Safari/537.36"


def _digits(n: int) -> str:
    return "".join(random.choice(string.digits) for _ in range(n))


def _ms_token() -> str:
    abc = string.ascii_letters + string.digits + "-_"
    return "".join(secrets.choice(abc) for _ in range(128))


def _ttwid() -> str:
    abc = string.ascii_letters + string.digits
    return "1%" + "".join(secrets.choice(abc) for _ in range(80))


class TikTokSession:
    def __init__(self, proxy: Optional[str] = None, mobile: bool = False):
        self.proxy = proxy
        self.ua = MOBILE_UA if mobile else DESKTOP_UA
        self.device_id = _digits(19)
        self.iid = _digits(19)
        self.ms_token = _ms_token()
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        kwargs = {}
        if self.proxy:
            kwargs["proxy"] = self.proxy
        self._client = httpx.AsyncClient(
            http2=True,
            timeout=httpx.Timeout(15.0, connect=10.0),
            headers={
                "User-Agent": self.ua,
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Origin": "https://www.tiktok.com",
                "Referer": "https://www.tiktok.com/",
                "Sec-Fetch-Site": "same-site",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Dest": "empty",
                "Cookie": f"msToken={self.ms_token}; ttwid={self._ttwid_cookie()};",
            },
            **kwargs,
        )
        return self

    @staticmethod
    def _ttwid_cookie() -> str:
        return _ttwid()

    async def __aexit__(self, *exc):
        if self._client:
            await self._client.aclose()

    def _base_params(self) -> Dict[str, str]:
        return {
            "aid": "1988",
            "app_language": "en-US",
            "app_name": "tiktok_web",
            "browser_language": "en-US",
            "browser_name": "Mozilla",
            "browser_online": "true",
            "browser_platform": "Win32",
            "browser_version": "5.0 (Windows)",
            "channel": "tiktok_web",
            "cookie_enabled": "true",
            "device_id": self.device_id,
            "device_platform": "web_pc",
            "focus_state": "true",
            "from_page": "user",
            "history_len": "5",
            "is_fullscreen": "false",
            "is_page_visible": "true",
            "language": "en",
            "os": "windows",
            "priority_region": "US",
            "referer": "",
            "region": "US",
            "screen_height": "1080",
            "screen_width": "1920",
            "tz_name": "UTC",
            "webcast_language": "en",
            "msToken": self.ms_token,
        }

    async def _signed_get(self, path: str, extra: Dict[str, str]) -> httpx.Response:
        p = self._base_params()
        p.update(extra)
        full = f"https://www.tiktok.com{path}?{urlencode(p)}"
        p["X-Bogus"] = await sign_xbogus(full, self.ua)
        return await self._client.get(f"{path}?{urlencode(p)}")

    async def _signed_post(self, path: str, extra: Dict[str, str]) -> httpx.Response:
        p = self._base_params()
        p.update(extra)
        full = f"https://www.tiktok.com{path}?{urlencode(p)}"
        p["X-Bogus"] = await sign_xbogus(full, self.ua)
        return await self._client.post(
            f"{path}?{urlencode(p)}",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            content="",
        )

    async def lookup_user(self, handle: str) -> Optional[Tuple[str, str]]:
        try:
            r = await self._signed_get(
                "/aweme/v1/web/user/profile/other/",
                {"unique_id": handle, "secUid": "", "publish_video_strategy_type": "2"},
            )
            data = r.json()
        except Exception:
            return None
        u = data.get("user") or {}
        uid = u.get("uid")
        sec = u.get("sec_uid")
        if uid and sec:
            return str(uid), str(sec)
        return None

    async def report_profile(self, user_id: str, sec_uid: str, handle: str, reason_id: int) -> httpx.Response:
        extra = {
            "object_id": user_id,
            "owner_id": user_id,
            "report_type": "user",
            "reason": str(reason_id),
            "report_reason": str(reason_id),
            "report_params": "",
            "target_user_id": user_id,
            "sec_user_id": sec_uid,
            "unique_id": handle,
            "extra": '{"report_type":"user"}',
        }
        return await self._signed_post("/aweme/v1/web/report/user/", extra)


# ------------------------------------------------------------------
# 3. JOB ENGINE
# ------------------------------------------------------------------
class JobRequest(BaseModel):
    username: str = Field(..., min_length=1)
    proxies: List[str] = Field(default_factory=list)
    report_count: int = Field(..., gt=0, le=100000)
    reason_id: int = Field(1004)
    concurrency: int = Field(20, gt=0, le=100)


class JobStatus(BaseModel):
    job_id: str
    username: str
    total: int
    sent: int
    success: int
    failed: int
    running: bool
    finished: bool
    errors: List[str] = []


@dataclass
class Job:
    job_id: str
    req: JobRequest
    total: int
    sent: int = 0
    success: int = 0
    failed: int = 0
    running: bool = True
    finished: bool = False
    errors: List[str] = field(default_factory=list)
    _subs: List[asyncio.Queue] = field(default_factory=list)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subs:
            self._subs.remove(q)

    async def emit(self) -> None:
        snap = {
            "job_id": self.job_id, "username": self.req.username,
            "total": self.total, "sent": self.sent, "success": self.success,
            "failed": self.failed, "running": self.running,
            "finished": self.finished, "errors": self.errors[-10:],
        }
        for q in list(self._subs):
            try: q.put_nowait(snap)
            except asyncio.QueueFull: pass


class ProxyPool:
    def __init__(self, urls: List[str]):
        self.pool = [{"url": u.strip(), "fails": 0, "dead": False} for u in urls if u.strip()]
        self._lock = asyncio.Lock()

    def empty(self) -> bool:
        return not self.pool

    async def pick(self) -> Optional[str]:
        async with self._lock:
            alive = [p for p in self.pool if not p["dead"]]
            if not alive:
                return None
            alive.sort(key=lambda p: p["fails"])
            top = alive[: max(1, len(alive) // 3)]
            return random.choice(top)["url"]

    async def fail(self, url: str, hard: bool = False) -> None:
        async with self._lock:
            for p in self.pool:
                if p["url"] == url:
                    p["fails"] += 1
                    if hard or p["fails"] >= 5:
                        p["dead"] = True
                    break

    async def ok(self, url: str) -> None:
        async with self._lock:
            for p in self.pool:
                if p["url"] == url:
                    p["fails"] = max(0, p["fails"] - 1)
                    break


JOBS: Dict[str, Job] = {}


async def run_job(job: Job) -> None:
    pool = ProxyPool(job.req.proxies)
    sem = asyncio.Semaphore(job.req.concurrency)
    handle = job.req.username.lstrip("@").strip()

    async def one() -> None:
        async with sem:
            proxy = await pool.pick() if not pool.empty() else None
            mobile = random.random() < 0.5
            try:
                async with TikTokSession(proxy=proxy, mobile=mobile) as s:
                    target = None
                    for _ in range(2):
                        target = await s.lookup_user(handle)
                        if target:
                            break
                        await asyncio.sleep(random.uniform(0.3, 1.0))
                    if not target:
                        job.failed += 1
                        job.errors.append("resolve_fail")
                        if proxy: await pool.fail(proxy)
                        return
                    uid, sec = target
                    r = await s.report_profile(uid, sec, handle, job.req.reason_id)
                    if r.status_code in (200, 201) and '"status_code":0' in r.text:
                        job.success += 1
                        if proxy: await pool.ok(proxy)
                    else:
                        job.failed += 1
                        job.errors.append(f"http_{r.status_code}")
                        if proxy: await pool.fail(proxy, hard=r.status_code in (401, 403, 429))
            except Exception as e:
                job.failed += 1
                job.errors.append(type(e).__name__)
                if proxy: await pool.fail(proxy)
            finally:
                job.sent += 1
                await asyncio.sleep(random.uniform(0.05, 0.4))
                if job.sent % 10 == 0 or job.sent == job.total:
                    await job.emit()

    tasks = [asyncio.create_task(one()) for _ in range(job.req.report_count)]
    try:
        await asyncio.gather(*tasks)
    finally:
        job.running = False
        job.finished = True
        await job.emit()


# ------------------------------------------------------------------
# 4. FASTAPI APP
# ------------------------------------------------------------------
app = FastAPI(title="TikTok Profile Reporter")


@app.get("/healthz")
async def healthz():
    return {"ok": "1"}


@app.post("/api/jobs", response_model=JobStatus)
async def create_job(req: JobRequest) -> JobStatus:
    jid = uuid.uuid4().hex[:12]
    job = Job(job_id=jid, req=req, total=req.report_count)
    JOBS[jid] = job
    asyncio.create_task(run_job(job))
    return JobStatus(job_id=jid, username=req.username, total=job.total,
                     sent=0, success=0, failed=0, running=True, finished=False)


@app.get("/api/jobs/{jid}", response_model=JobStatus)
async def get_job(jid: str) -> JobStatus:
    job = JOBS.get(jid)
    if not job:
        raise HTTPException(404, "not found")
    return JobStatus(job_id=job.job_id, username=job.req.username,
                     total=job.total, sent=job.sent, success=job.success,
                     failed=job.failed, running=job.running,
                     finished=job.finished, errors=job.errors[-25:])


@app.websocket("/ws/{jid}")
async def ws(websocket: WebSocket, jid: str):
    await websocket.accept()
    job = JOBS.get(jid)
    if not job:
        await websocket.send_json({"error": "job not found"})
        await websocket.close()
        return
    q = job.subscribe()
    try:
        await websocket.send_json({
            "job_id": job.job_id, "username": job.req.username,
            "total": job.total, "sent": job.sent, "success": job.success,
            "failed": job.failed, "running": job.running,
            "finished": job.finished, "errors": job.errors[-10:],
        })
        while True:
            snap = await q.get()
            await websocket.send_json(snap)
            if snap["finished"]:
                break
    except WebSocketDisconnect:
        pass
    finally:
        job.unsubscribe(q)
        try: await websocket.close()
        except Exception: pass


# ------------------------------------------------------------------
# 5. UI — served from memory
# ------------------------------------------------------------------
INDEX_HTML = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>tiktok profile reporter</title>
<style>
:root{--bg:#0b0d10;--panel:#12151a;--border:#1f242c;--text:#e7ebf0;--muted:#8b94a3;--accent:#ff2e63;--ok:#34d399;--err:#f87171}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 ui-monospace,Menlo,monospace}
header{padding:20px 28px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:12px}
header h1{font-size:16px;margin:0;letter-spacing:.5px}
.dot{width:10px;height:10px;border-radius:50%;background:var(--accent);box-shadow:0 0 12px var(--accent)}
main{max-width:980px;margin:0 auto;padding:24px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.panel{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:16px}
label{display:block;color:var(--muted);font-size:12px;margin-bottom:6px;text-transform:uppercase;letter-spacing:.8px}
input,textarea,button{width:100%;background:#0a0c0f;color:var(--text);border:1px solid var(--border);border-radius:8px;padding:10px 12px;font:inherit;outline:none}
input:focus,textarea:focus{border-color:var(--accent)}
textarea{min-height:160px;resize:vertical}
button{background:var(--accent);color:#fff;border:none;cursor:pointer;font-weight:700;letter-spacing:.4px;margin-top:8px}
button:disabled{opacity:.5;cursor:not-allowed}
.row{display:flex;gap:12px}.row>*{flex:1}
.stat{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px dashed var(--border)}
.stat:last-child{border-bottom:none}
.stat .k{color:var(--muted)}.stat .v{font-weight:700}
.ok{color:var(--ok)}.err{color:var(--err)}
.log{max-height:220px;overflow:auto;background:#08090b;border:1px solid var(--border);border-radius:8px;padding:10px;font-size:12px}
.log div{padding:2px 0;color:var(--muted)}
.bar{height:8px;border-radius:4px;background:#0a0c0f;overflow:hidden;border:1px solid var(--border);margin-top:10px}
.bar>i{display:block;height:100%;width:0%;background:linear-gradient(90deg,#ff2e63,#ff8a3d);transition:width .2s}
</style></head><body>
<header><span class="dot"></span><h1>tiktok profile reporter</h1></header>
<main><div class="grid">
<div class="panel">
<label>target username (no @)</label><input id="username" placeholder="username"/>
<div style="height:12px"></div>
<label>reason id</label><input id="reason_id" type="number" value="1004"/>
<div style="height:12px"></div>
<div class="row">
<div><label>report count</label><input id="report_count" type="number" value="500"/></div>
<div><label>concurrency</label><input id="concurrency" type="number" value="20"/></div>
</div>
<div style="height:12px"></div>
<label>proxies (one per line, optional)</label>
<textarea id="proxies" placeholder="http://user:pass@host:port&#10;socks5://host:port"></textarea>
<button id="go">start reporting</button>
</div>
<div class="panel">
<label>status</label>
<div class="stat"><span class="k">job id</span><span class="v" id="s_job">—</span></div>
<div class="stat"><span class="k">sent</span><span class="v" id="s_sent">0</span></div>
<div class="stat"><span class="k">success</span><span class="v ok" id="s_success">0</span></div>
<div class="stat"><span class="k">failed</span><span class="v err" id="s_failed">0</span></div>
<div class="stat"><span class="k">running</span><span class="v" id="s_running">no</span></div>
<div class="bar"><i id="bar"></i></div>
<div style="height:12px"></div>
<label>log</label><div class="log" id="log"></div>
</div>
</div></main>
<script>
const $=id=>document.getElementById(id);
let ws=null;
function log(t,c){const d=document.createElement("div");d.textContent=t;if(c)d.className=c;$("log").prepend(d);}
function render(s){
$("s_job").textContent=s.job_id||"—";
$("s_sent").textContent=s.sent;$("s_success").textContent=s.success;
$("s_failed").textContent=s.failed;$("s_running").textContent=s.running?"yes":"no";
const pct=s.total?Math.min(100,Math.round(s.sent/s.total*100)):0;
$("bar").style.width=pct+"%";
if(s.errors&&s.errors.length){$("log").innerHTML="";s.errors.slice().reverse().forEach(e=>log("err: "+e,"err"));}
}
$("go").onclick=async()=>{
const username=$("username").value.trim();
if(!username)return alert("username required");
const body={username,reason_id:parseInt($("reason_id").value||"1004",10),
report_count:parseInt($("report_count").value||"100",10),
concurrency:parseInt($("concurrency").value||"20",10),
proxies:$("proxies").value.split("\\n").map(x=>x.trim()).filter(Boolean)};
$("go").disabled=true;$("log").innerHTML="";log("creating job...");
try{
const r=await fetch("/api/jobs",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
if(!r.ok)throw new Error(await r.text());
const job=await r.json();
log("job "+job.job_id+" started");
if(ws)ws.close();
const proto=location.protocol==="https:"?"wss":"ws";
ws=new WebSocket(`${proto}://${location.host}/ws/${job.job_id}`);
ws.onmessage=ev=>{const s=JSON.parse(ev.data);render(s);
if(s.finished){log("finished. success="+s.success+" failed="+s.failed);$("go").disabled=false;}};
ws.onclose=()=>{$("go").disabled=false;};
}catch(e){log("error: "+e.message,"err");$("go").disabled=false;}
};
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(INDEX_HTML)