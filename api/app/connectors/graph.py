"""Microsoft Graph connector（app-only，client credentials）。

真實租戶與 mock 走同一份程式：token 端點都是 POST {login_base}/{tenant}/oauth2/v2.0/token，
差別只在 login_base 與 graph_base 指向哪裡。
"""

from dataclasses import dataclass
import httpx

from app.connectors.http import Retrying

USER_FIELDS = ["displayName", "givenName", "surname", "userPrincipalName", "mail", "accountEnabled", "employeeId",
               "employeeType", "department", "jobTitle", "officeLocation", "userType", "createdDateTime",
               "externalUserState"]


class GraphFailure(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"{status} {code}: {message}")
        self.status, self.code = status, code


@dataclass
class GraphApp:
    tenant: str
    client_id: str
    client_secret: str


class GraphClient:
    def __init__(self, http: httpx.Client, app: GraphApp, graph_base: str, login_base: str, **retry):
        self.rt = Retrying(http, **retry)
        self.app, self.graph_base, self.login_base = app, graph_base.rstrip("/"), login_base.rstrip("/")
        self._token: str | None = None

    def _fetch_token(self) -> str:
        r = self.rt.request("POST", f"{self.login_base}/{self.app.tenant}/oauth2/v2.0/token", data={
            "client_id": self.app.client_id, "client_secret": self.app.client_secret,
            "grant_type": "client_credentials", "scope": "https://graph.microsoft.com/.default"})
        if r.status_code != 200:
            raise GraphFailure(r.status_code, r.json().get("error", "token_error"), "無法取得 token，請檢查 App 憑證")
        return r.json()["access_token"]

    def call(self, method: str, url: str, **kw) -> httpx.Response:
        if not url.startswith("http"):
            url = f"{self.graph_base}{url}"
        for refreshed in (False, True):
            if self._token is None:
                self._token = self._fetch_token()
            r = self.rt.request(method, url, headers={"Authorization": f"Bearer {self._token}"}, **kw)
            if r.status_code == 401 and not refreshed:
                self._token = None  # token 過期：重取一次
                continue
            return r
        return r

    def get(self, url: str) -> dict:
        r = self.call("GET", url)
        if r.status_code != 200:
            err = r.json().get("error", {})
            raise GraphFailure(r.status_code, err.get("code", ""), err.get("message", ""))
        return r.json()

    def pages(self, url: str) -> list[dict]:
        items = []
        while url:
            body = self.get(url)
            items += body["value"]
            url = body.get("@odata.nextLink")
        return items

    def delta(self, url: str) -> tuple[list[dict], str]:
        """跟著 nextLink 走到底，回傳所有變動與下一次要用的 deltaLink。"""
        items = []
        while True:
            body = self.get(url)
            items += body["value"]
            if "@odata.nextLink" in body:
                url = body["@odata.nextLink"]
            else:
                return items, body["@odata.deltaLink"]

    # ---------- 讀 ----------
    def users_delta(self, delta_link: str | None) -> tuple[list[dict], str]:
        return self.delta(delta_link or f"/v1.0/users/delta?$select={','.join(USER_FIELDS)}")

    def groups_delta(self, delta_link: str | None) -> tuple[list[dict], str]:
        return self.delta(delta_link or "/v1.0/groups/delta?$select=displayName,description,members")

    def sign_in_activity(self) -> dict[str, dict | None] | None:
        """回傳 {使用者 id: signInActivity}。租戶沒有 P1/P2 授權時回 None（殭屍帳號規則就無法判斷）。"""
        try:
            items = self.pages("/v1.0/users?$select=id,signInActivity&$top=120")
        except GraphFailure as e:
            if e.code == "Authentication_RequestFromNonPremiumTenantOrB2CTenant":
                return None
            raise
        return {u["id"]: u.get("signInActivity") for u in items}

    def role_definitions(self) -> list[dict]:
        return self.get("/v1.0/roleManagement/directory/roleDefinitions")["value"]

    def role_assignments(self) -> list[dict]:
        return self.pages("/v1.0/roleManagement/directory/roleAssignments")
