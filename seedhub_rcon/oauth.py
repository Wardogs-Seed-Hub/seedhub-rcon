"""Discord identity only. OAuth tokens are never persisted."""
import re

from authlib.integrations.httpx_client import AsyncOAuth2Client

from .errors import Problem

AUTHORIZE = "https://discord.com/oauth2/authorize"
TOKEN = "https://discord.com/api/oauth2/token"
IDENTITY = "https://discord.com/api/v10/users/@me"


class DiscordOAuth:
    def __init__(self, settings):
        self.settings = settings

    def client(self):
        return AsyncOAuth2Client(
            self.settings.client_id, self.settings.client_secret,
            redirect_uri=self.settings.callback, scope="identify",
            timeout=10, trust_env=False, follow_redirects=False)

    async def url(self, state):
        async with self.client() as client:
            url, _ = client.create_authorization_url(AUTHORIZE, state=state, prompt="consent")
            return url

    async def identity(self, code):
        try:
            async with self.client() as client:
                await client.fetch_token(TOKEN, code=code, grant_type="authorization_code")
                response = await client.get(IDENTITY)
                if response.status_code != 200:
                    raise ValueError("Identity unavailable")
                user = response.json()
                uid = user.get("id")
                if not isinstance(uid, str) or not re.fullmatch(r"[0-9]{17,20}", uid):
                    raise ValueError("Invalid identity")
                return uid
        except Exception:
            raise Problem(503, "login_unavailable", "Discord sign-in is unavailable. Please try again.") from None
