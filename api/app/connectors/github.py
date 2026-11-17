"""GitHub organization connector（REST，Link header 分頁）。"""

import re

import httpx

from app.connectors.http import Retrying

NEXT = re.compile(r'<([^>]+)>;\s*rel="next"')


class GitHubFailure(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"{status}: {message}")
        self.status = status


class GitHubClient:
    def __init__(self, http: httpx.Client, base: str, org: str, token: str, **retry):
        self.rt = Retrying(http, **retry)
        self.base, self.org = base.rstrip("/"), org
        self.headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28"}

    def call(self, method: str, path: str, **kw) -> httpx.Response:
        url = path if path.startswith("http") else f"{self.base}{path}"
        return self.rt.request(method, url, headers=self.headers, **kw)

    def pages(self, path: str) -> list[dict]:
        items, url = [], f"{path}{'&' if '?' in path else '?'}per_page=100"
        while url:
            r = self.call("GET", url)
            if r.status_code != 200:
                raise GitHubFailure(r.status_code, r.json().get("message", ""))
            items += r.json()
            m = NEXT.search(r.headers.get("Link", ""))
            url = m.group(1) if m else None
        return items

    def members(self) -> list[dict]:
        return self.pages(f"/orgs/{self.org}/members")

    def admins(self) -> set[str]:
        return {m["login"] for m in self.pages(f"/orgs/{self.org}/members?role=admin")}

    def without_2fa(self) -> set[str]:
        return {m["login"] for m in self.pages(f"/orgs/{self.org}/members?filter=2fa_disabled")}

    def outside_collaborators(self) -> list[dict]:
        return self.pages(f"/orgs/{self.org}/outside_collaborators")

    def profile(self, login: str) -> dict:
        r = self.call("GET", f"/users/{login}")
        if r.status_code != 200:
            raise GitHubFailure(r.status_code, r.json().get("message", ""))
        return r.json()
