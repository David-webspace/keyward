"""Mock 的記憶體狀態：從 data/synthetic 載入，所有寫入都記版本，給 delta query 用。"""

import base64
import json
from dataclasses import dataclass, field
from pathlib import Path


def enc(obj: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj, separators=(",", ":")).encode()).decode().rstrip("=")


def dec(token: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))


@dataclass
class Faults:
    throttle_every: int = 0      # 每第 N 個請求回 429（0 = 關閉）
    retry_after: int = 1
    fail_writes: list[int] = field(default_factory=list)   # 第幾次寫入回 503（從 1 起算），不會生效
    silent_ids: list[str] = field(default_factory=list)    # 對這些物件的寫入回成功但其實沒生效
    premium: bool = True         # False 模擬 Entra ID 免費層：讀 signInActivity 會被拒


class WriteFailed(Exception):
    pass


class Store:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.faults = Faults()
        self.reset()

    def reset(self):
        e = json.loads((self.data_dir / "entra.json").read_text())
        g = json.loads((self.data_dir / "github.json").read_text())
        self.users = {u["id"]: u for u in e["users"]}
        self.groups = {x["id"]: x for x in e["groups"]}
        self.members = {gid: list(e["members"].get(gid, [])) for gid in self.groups}
        self.role_defs = e["roleDefinitions"]
        self.role_assignments = {a["id"]: a for a in e["roleAssignments"]}
        self.deleted_users: dict[str, dict] = {}
        self.version = 0
        self.user_log: list[tuple[int, str]] = []                 # (版本, 使用者 id)
        self.member_log: list[tuple[int, str, str, bool]] = []    # (版本, 群組 id, 成員 id, 是否移除)
        self.gh_org = g["org"]
        self.gh_members = {m["login"]: m for m in g["members"]}
        self.gh_outside = {m["login"]: m for m in g["outside_collaborators"]}
        self.gh_teams = {t["slug"]: t for t in g["teams"]}
        self.gh_team_members = {k: list(v) for k, v in g["team_members"].items()}
        self.gh_invitations: dict[str, dict] = {}
        self.requests = 0
        self.writes = 0
        self.applied_writes = 0
        self.tokens: dict[str, set[str]] = {}

    def bump(self) -> int:
        self.version += 1
        return self.version

    def write_gate(self, target_id: str) -> bool:
        """每次寫入都先過這裡。回傳 False 代表要假裝成功但不套用。"""
        self.writes += 1
        if self.writes in self.faults.fail_writes:
            raise WriteFailed
        if target_id in self.faults.silent_ids:
            return False
        self.applied_writes += 1
        return True

    def find_user(self, key: str) -> dict | None:
        if key in self.users:
            return self.users[key]
        low = key.lower()
        return next((u for u in self.users.values() if (u["userPrincipalName"] or "").lower() == low), None)
