"""HTTP application. Construct explicitly; never connect to RCON on startup."""
import ipaddress
import logging
from pathlib import Path
import secrets
import sqlite3
import time
from urllib.parse import urlsplit

from aiohttp import web
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .database import Database
from .errors import Problem
from .oauth import DiscordOAuth
from .rcon import Rcon, server_uuid
from .security import digest, equal, token
from .service import Service, stamp

STATE = web.AppKey("state", object)
COOKIE = "__Host-seedhub_session"
OAUTH_COOKIE = "__Host-seedhub_oauth"
templates = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"),
                        autoescape=select_autoescape(["html"]))


def render(request, page, status=200, **data):
    state = request.app[STATE]
    session = state.db.session(request.cookies.get(COOKIE))
    return web.Response(text=templates.get_template("page.html").render(
        page=page, session=session, origin=state.settings.public_url,
        support=state.settings.support_url, stamp=stamp, **data),
        status=status, content_type="text/html")


def session(request, fresh=False):
    state = request.app[STATE]
    found = state.db.session(request.cookies.get(COOKIE))
    if not found:
        raise Problem(401, "signin_required", "Please sign in with Discord.")
    if fresh and time.time() - found["created_at"] > 900:
        raise Problem(401, "signin_required", "Please sign in again before changing this connection.")
    if "*" not in state.settings.allowed_users and found["owner"] not in state.settings.allowed_users:
        raise Problem(403, "access_denied", "This test instance is not open to your account.")
    return found


async def form(request, fresh=True):
    found = session(request, fresh=fresh)
    if request.headers.get("Origin") != request.app[STATE].settings.public_url:
        raise Problem(403, "invalid_form", "Reload this page and try again.")
    if request.content_type != "application/x-www-form-urlencoded":
        raise Problem(400, "invalid_form", "Unsupported form format.")
    data = await request.post()
    if any(len(data.getall(k)) != 1 for k in data):
        raise Problem(400, "invalid_form", "Duplicate form fields are not supported.")
    if not equal(data.get("csrf", ""), found["csrf"]):
        raise Problem(403, "invalid_form", "Reload this page and try again.")
    return found, data


def cookie(response, name, value, age):
    response.set_cookie(name, value, max_age=age, secure=True, httponly=True,
                        samesite="Lax", path="/")


def clear_cookie(response, name):
    # Expiring a __Host- cookie must preserve Secure, Path=/ and no Domain.
    cookie(response, name, "", 0)


@web.middleware
async def boundary(request, handler):
    state = request.app[STATE]
    try:
        if request.host != urlsplit(state.settings.public_url).netloc:
            raise Problem(400, "invalid_host", "Use this service's configured domain.")
        if request.query_string and request.path != "/auth/discord/callback":
            raise Problem(400, "invalid_request", "Query parameters are not supported here.")
        peer = request.remote or "unknown"
        # Only the loopback-bound listener receives Tunnel traffic. Arbitrary
        # X-Forwarded-For values are ignored.
        try:
            if ipaddress.ip_address(peer).is_loopback:
                candidate = request.headers.get("CF-Connecting-IP", peer)
                peer = str(ipaddress.ip_address(candidate))
        except ValueError:
            pass
        state.db.cleanup()
        state.db.limit("global", 1200, 60)
        state.db.limit("peer:" + peer, 120, 60)
        if request.path == "/auth/discord":
            state.db.limit("login:" + peer, 5, 60)
        response = await handler(request)
    except Problem as exc:
        if request.path == "/auth/discord/callback":
            # Keep OAuth codes/state off rendered pages and subsequent referrers.
            response = web.HTTPSeeOther("/login-failed")
            clear_cookie(response, OAUTH_COOKIE)
        elif request.path.startswith("/api/"):
            response = web.json_response({"error": {"code": exc.code, "message": exc.message}}, status=exc.status)
        else:
            response = render(request, "error", status=exc.status, message=exc.message)
        if exc.retry:
            response.headers["Retry-After"] = str(exc.retry)
    except web.HTTPException as exc:
        response = exc
    except Exception:
        # Intentionally never log exception text, URLs, headers, or request bodies.
        logging.error("Request failed; details suppressed to protect credentials.")
        if request.path.startswith("/api/"):
            response = web.json_response({"error": {"code": "service_unavailable",
                "message": "The service is temporarily unavailable."}}, status=503)
        else:
            response = web.Response(text="Temporarily unavailable. Please try again.", status=503)
    # no-referrer makes native form POSTs send Origin: null. Preserve same-origin
    # forms while keeping OAuth callback parameters out of redirect referrers.
    referrer_policy = "no-referrer" if request.path == "/auth/discord/callback" else "same-origin"
    response.headers.update({
        "Cache-Control": "no-store", "Pragma": "no-cache",
        "Referrer-Policy": referrer_policy, "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY", "Strict-Transport-Security": "max-age=31536000",
        "Content-Security-Policy": "default-src 'none'; style-src 'self'; script-src 'self'; "
            "img-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()"})
    response.headers.pop("Server", None)
    if isinstance(response, web.HTTPException):
        normalized = web.Response(status=response.status, headers=response.headers, body=response.body)
        normalized.cookies.update(response.cookies)
        response = normalized
    return response


class State:
    def __init__(self, settings, db, transport, oauth):
        self.settings, self.db, self.oauth = settings, db, oauth
        self.service = Service(db, transport)


async def home(request):
    state = request.app[STATE]
    found = state.db.session(request.cookies.get(COOKIE))
    if found:
        found = session(request)
        rows = state.db.all("SELECT * FROM connections WHERE owner=? ORDER BY created_at DESC", found["owner"])
        return render(request, "dashboard", rows=rows)
    return render(request, "landing")


async def login(request):
    state = request.app[STATE]
    raw, browser = token(), token()
    with state.db.conn:
        state.db.conn.execute("INSERT INTO oauth VALUES (?,?,?)", (digest(raw), digest(browser), time.time()+300))
    response = web.HTTPFound(await state.oauth.url(raw))
    cookie(response, OAUTH_COOKIE, browser, 300)
    return response


async def callback(request):
    state = request.app[STATE]
    if any(len(request.query.getall(k)) != 1 for k in request.query):
        raise Problem(400, "invalid_login", "Sign-in could not be verified.")
    raw = request.query.get("state", "")
    code = request.query.get("code", "")
    browser = request.cookies.get(OAUTH_COOKIE, "")
    if not 1 <= len(raw) <= 128 or not 1 <= len(code) <= 2048 or len(browser) > 128:
        raise Problem(400, "invalid_login", "Sign-in could not be verified.")
    with state.db.conn:
        attempt = state.db.one("SELECT * FROM oauth WHERE state_hash=?", digest(raw))
        if attempt:
            state.db.conn.execute("DELETE FROM oauth WHERE state_hash=?", (digest(raw),))
    if (not attempt or attempt["expires"] <= time.time()
            or not equal(attempt["browser_hash"], digest(browser))):
        raise Problem(400, "invalid_login", "Sign-in could not be verified.")
    owner = await state.oauth.identity(code)
    if "*" not in state.settings.allowed_users and owner not in state.settings.allowed_users:
        raise Problem(403, "access_denied", "This test instance is not open to your account.")
    old = request.cookies.get(COOKIE, "")
    with state.db.conn:
        state.db.conn.execute("DELETE FROM sessions WHERE hash=?", (digest(old),))
        state.db.audit(owner, "login")
    response = web.HTTPSeeOther("/")
    cookie(response, COOKIE, state.db.new_session(owner), 4*3600)
    clear_cookie(response, OAUTH_COOKIE)
    return response


async def logout(request):
    found, _ = await form(request, fresh=False)
    with request.app[STATE].db.conn:
        request.app[STATE].db.conn.execute("DELETE FROM sessions WHERE hash=?", (found["hash"],))
    response = web.HTTPSeeOther("/")
    clear_cookie(response, COOKIE)
    return response


async def new_page(request):
    session(request)
    return render(request, "form", row=None)


async def save(request):
    found, data = await form(request)
    cid = request.match_info.get("cid")
    cid = await request.app[STATE].service.save(found["owner"], data,
        lambda: session(request, fresh=True), cid)
    return web.HTTPSeeOther("/connections/" + cid)


async def details(request):
    found = session(request)
    row = request.app[STATE].db.owned(request.match_info["cid"], found["owner"])
    return render(request, "detail", row=row)


async def edit_page(request):
    found = session(request)
    row = request.app[STATE].db.owned(request.match_info["cid"], found["owner"])
    return render(request, "form", row=row)


async def action(request):
    found, data = await form(request)
    state = request.app[STATE]
    cid, operation = request.match_info["cid"], request.match_info["action"]
    row = state.db.owned(cid, found["owner"])
    if operation == "test":
        await state.service.test(found["owner"], cid, lambda: session(request, fresh=True))
    else:
        if data.get("confirm") != "yes":
            return render(request, "confirm", row=row, operation=operation)
        raw = state.service.change(found["owner"], cid, operation)
        if raw:
            return render(request, "key", row=row, api_key=raw)
    return web.HTTPSeeOther("/" if operation == "delete" else "/connections/" + cid)


async def api(request):
    auth = request.headers.get("Authorization", "")
    raw = auth[7:] if auth.startswith("Bearer ") else ""
    return web.json_response(await request.app[STATE].service.read(raw, server_uuid(request.match_info["uuid"])))


async def health(request):
    request.app[STATE].db.one("SELECT 1")
    return web.json_response({"status": "ok"})


async def login_failed(request):
    return render(request, "error", status=401,
                  message="Sign-in could not be completed. Try again, or ask the operator whether your Discord account is allowed.")


async def static(request):
    name = request.match_info["name"]
    types = {"style.css": "text/css", "app.js": "application/javascript",
             "seedhub-logo.jpg": "image/jpeg"}
    if name not in types:
        raise web.HTTPNotFound()
    return web.Response(body=(Path(__file__).parent/"static"/name).read_bytes(),
                        content_type=types[name])


def create_app(settings, db, transport=None, oauth=None):
    app = web.Application(middlewares=[boundary], client_max_size=16384)
    app[STATE] = State(settings, db, transport or Rcon(settings), oauth or DiscordOAuth(settings))
    app.add_routes([
        web.get("/", home), web.get("/healthz", health),
        web.get("/auth/discord", login), web.get("/auth/discord/callback", callback),
        web.get("/login-failed", login_failed), web.post("/logout", logout),
        web.get("/connections/new", new_page), web.post("/connections/new", save),
        web.get("/connections/{cid}", details), web.get("/connections/{cid}/edit", edit_page),
        web.post("/connections/{cid}/edit", save),
        web.post("/connections/{cid}/{action}", action),
        web.get("/api/{uuid}/playerlist", api, allow_head=False),
        web.get("/static/{name}", static)])
    return app
