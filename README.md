# keyward

跨平台帳號權限盤點助理：以 Microsoft Entra ID 為身分主軸，把 Entra ID、GitHub、ERP 上的帳號和權限對回 HR 名冊，找出離職未停用、轉調未收回、過期來賓、殭屍帳號、權限過大、職責分離衝突。主管覆核後安全地撤銷，並留下稽核證據。

所有資料都是虛構的（Arcwell Electronics，約 650 人），Microsoft Graph 與 GitHub 由本機 mock 提供，**不需要任何雲端帳號就能完整跑起來**。

![主管的覆核頁：每個項目是一張鑰匙吊牌，決定後蓋上「撤銷」「保留」或「部分撤銷」](docs/screenshots/reviews-decided.png)

<sub>主管的「我的覆核」：系統用白話說明為什麼要覆核，主管決定保留或撤銷；權限明顯多於同事的人，可以逐個群組決定。</sub>

| | |
|---|---|
| ![規則頁：AI 把一句話轉成規則，並試算套用後會多出哪些問題](docs/screenshots/policy.png) | ![活動頁：依類型看進度、還在等誰、交付執行、下載證據包](docs/screenshots/campaign.png) |
| **規則**：一句話轉成規則並預覽影響；右邊是一筆被程式擋下的 AI 建議（把「CRM」當成部門代碼）。 | **覆核活動**：137 個項目的進度、還在等誰、提醒與升級、交付執行、稽核證據包。 |
| ![查人：一個人在各系統的權限，以及間接權限經由哪個群組取得](docs/screenshots/person.png) | ![發現：依規則分類的所有問題](docs/screenshots/findings.png) |
| **查人**：轉調後還留在舊單位群組，因此間接拿到人事檔案與薪資資料。 | **發現**：依規則分類的所有問題，判斷不經過 AI。 |

## 快速開始

需要：[Docker Desktop](https://www.docker.com/products/docker-desktop/)（macOS、Windows、Linux 皆可）。

```bash
git clone https://github.com/David-webspace/keyward.git
cd keyward
./setup.sh
docker compose up -d --build
```

- `./setup.sh` 會產生 `.env`（隨機的密碼與 mock 憑證），已存在就略過。Windows 請在 Git Bash 或 WSL 執行。
- 第一次建置約 2–3 分鐘。API 啟動時會自動產生擬真資料並完成第一次同步。

全部起來後打開：

| 網址 | 內容 |
|---|---|
| http://localhost:3500 | **前端**（從這裡開始） |
| http://localhost:8027 | 通知信收件匣（Mailpit，所有信都寄到這裡，不會寄到真實信箱） |
| http://localhost:8390/health | 覆核 API |
| http://localhost:8391/health | Microsoft Graph 與 GitHub 的 mock |

### 五分鐘導覽

1. 登入頁點 **羅鈺文**（資安負責人・IT 管理者）→「覆核活動」→ 用最新同步建立並分派。系統會依主管關係分派 137 個項目，每位主管收到一封信（看 Mailpit）。
2. 登出，回登入頁改點一位**主管**（例如財務主管劉欣涵），在「我的覆核」對吊牌選擇保留或撤銷。
3. 換回羅鈺文，在活動頁選一個日期按「推到這天」，看到期提醒與逾期升級；再按「交付執行」、「下載 zip」取得稽核證據包。
4. 「發現」看所有問題、「查人」看一個人在所有系統的權限，以及間接權限是經由哪個群組取得的。

### 選用：開啟 AI 規則提案

沒設定模型時 AI 功能會停用，其他功能照常。要開啟，在 `.env` 加上模型設定，例如接本機的 [Ollama](https://ollama.com)（先 `ollama pull qwen3.5:9b`）：

```bash
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_MODEL=qwen3.5:9b
LLM_REASONING_EFFORT=none
```

改用 Claude 則設 `LLM_PROVIDER=anthropic`、`LLM_MODEL`、`LLM_API_KEY`。改完執行 `docker compose up -d api` 讓設定生效。

### 停止與重來

```bash
docker compose down              # 停止（資料保留）
docker compose down -v           # 停止並清空資料庫
```

要完全回到初始狀態，再刪掉 `data/state/`（同步快照與執行帳本）。擬真資料每次啟動都會用固定種子重新產生，結果相同。

### 常見問題

- **連接埠被占用**：在 `.env` 改 `WEB_PORT`、`API_PORT`、`MOCK_PORT`、`DB_PORT`、`MAIL_UI_PORT`，再重新 `docker compose up -d`。
- **建置時拉不到映像、一直逾時**：先確認 Docker Desktop 的網路與 Proxy 設定能連到 Docker Hub 與 ghcr.io。
- **想看服務記錄**：`docker compose logs api`（或 `web`、`mock`）。

## 擬真資料

公司 Arcwell Electronics 與所有人名、帳號都是虛構的，Email 一律使用保留網域 `.example`。資料由固定種子產生，每次結果相同。

| 項目 | 規模 |
|---|---|
| 據點 | 9 個（台北總部、桃園、新竹、東莞、越南北寧、泰國春武里新廠、聖荷西、東京、慕尼黑） |
| HR 名冊 | 650 名在職（含 6 名留職停薪）、123 筆離職紀錄、76 筆轉調 |
| Entra ID | 721 個成員帳號、60 名外部來賓、176 個群組（含巢狀）、23 個目錄角色指派 |
| GitHub | 86 名成員、5 名外部協作者、12 個團隊 |
| ERP | 30 個角色、332 筆角色指派、8 條職責分離規則 |

刻意埋入 162 筆問題作為評測標準答案，另有 40 筆「看起來可疑但其實合理」的干擾項（留職停薪、重新聘用、約聘轉正、預告離職、跨廠支援、緊急存取帳號、服務帳號等），用來量測誤報。數量見 `data/synthetic/manifest.json`。

## Mock 伺服器

照官方文件的行為實作，讓離線示範與評測結果可重現：

- **Graph**：client credentials 取 token、`@odata.nextLink` 分頁、`users/delta` 與 `groups/delta`（含 `members@delta`）、`transitiveMemberOf`、停用帳號、移出群組、刪除與還原來賓、目錄角色指派。
- **權限**：唯讀 App 與寫入 App 分開，權限不足回 `Authorization_RequestDenied`；選 `signInActivity` 需要 `AuditLog.Read.All` 與 P1/P2 授權，且每頁最多 120 筆；目標擔任管理員角色時無法停用。
- **GitHub**：Link header 分頁、`filter=2fa_disabled`、移除成員與外部協作者；重新加入只會產生 pending 邀請，無法真正還原。
- **故障注入**（`PUT /_mock/faults`）：429 與 `Retry-After`、指定第幾次寫入失敗、寫入回成功但其實沒生效。

## 同步與發現規則

- **同步**（`python -m app.sync`）：Entra 使用者與群組用 delta query 增量同步；`signInActivity` 不支援 delta，另外全量讀；429／5xx 依 `Retry-After` 重試；token 過期自動重取。快照存在 `data/state/snapshots/`。
- **身分對應**：Entra 依 employeeId（含轉正前舊編號）→ UPN；GitHub 依 IT 的帳號登記表或公開 Email。只有姓名或帳號名稱相符的列為候選，**一律只建議確認身分，不直接移除**。
- **發現規則**（`python -m app.findings`）：全部依 `api/app/policy.yaml` 判定，不經過模型。同一個根因（例如一個直接加入的群組帶來三個敏感資源）只報一次。
- **評測**（`python -m app.evals.score`）：162 筆全部找到、0 筆多報、干擾項 0 筆誤報；另外用 10 個沒參與調參的種子重跑（一半開啟限流），1,605 筆全部找到、0 筆多報。詳見 [api/eval/REPORT.md](api/eval/REPORT.md)，包含限制說明。

## 覆核流程

IT 從一次同步建立覆核活動（`POST /campaigns`），系統依 HR 主管關係自動分派：

| 發現 | 覆核者 |
|---|---|
| 轉調未收回、敏感資源、殭屍帳號、同儕離群、職責分離 | 當事人的主管 |
| 外部來賓 | 贊助人；贊助人已離職則為其主管；沒有登記則為資安負責人 |
| 多餘的管理員、GitHub 身分不明、未開 2FA | 資安負責人 |
| 已離職 | 不需覆核，HR 名冊即依據，直接交付執行並等 IT 核准 |

- 每位覆核者收到一封彙整信（Mailpit），期限 7 天；到期前 2 天提醒；逾期升級給上一層主管再給 3 天；到最上層仍未決定就標成逾期交給資安。**逾期不會自動撤銷。**
- 保留必須寫理由，最長 1 年，期間同一個發現不再列出，到期後重新出現；來賓保留要填新的到期日；同儕離群逐個群組決定。
- 主管只看得到指派給自己的項目，別人的一律回 404；IT 管理者看得到全部，但不能代替主管決定。
- 交付執行（`POST /campaigns/{id}/hand-off`）：主管撤銷的動作在執行帳本裡記為已核准（核准者是主管），已離職與不可逆的動作留給 IT 另外核准。
- 給主管看的說明由固定模板產生，內容來自發現依據與群組說明，不經過模型。
- 登入目前是示範模式（從 HR 名冊選人，`AUTH_MODE=demo`），正式環境改用 Entra ID SSO（尚未實作）。

## AI 規則提案

模型只用在一個地方：**產生規則變更提案**。誰該撤權仍然只由規則與主管決定。

```
群組標註：群組 → 模型建議敏感度、擁有部門、可存取對象 ┐
                                                  ├→ 程式驗證 → 影響預覽 → IT 套用 → 疊加在 policy.yaml 上生效
一句話寫規則：「薪資資料只有台北的人資和財務能看」  ┘
```

- **為什麼需要群組標註**：policy.yaml 只列了 14 個敏感資源，其他 92 個群組規則根本看不到。擬真資料刻意埋了 3 個這類問題：客戶端的外部來賓被加進內部的報價審查專案。只有群組被標成限制級之後，才會被抓到。
- **程式驗證**：部門、據點、群組、交易代碼必須真的存在；模型引用的依據必須逐字出現在輸入裡，防止捏造理由。沒通過驗證的提案不能套用，IT 可以修改後再套用。
- **影響預覽**：用最新同步重跑發現規則，列出套用後會多出、會消失哪些發現。
- **一句話寫規則**支援資源存取對象、職責分離、門檻三種；意思不清楚或資源不存在時必須反問，不能猜。
- 規則提案和核准紀錄都會放進稽核證據包（`policy_changes.csv`）。
- 模型可接 Claude（`LLM_PROVIDER=anthropic`）或任何 OpenAI 相容伺服器（Ollama、vLLM、Azure OpenAI）。沒設定時這兩個功能停用，其他功能不受影響。

評測（`python -m app.evals.ai_eval`，本機 `qwen3.5:9b`，兩次執行）：

| | 第一輪 | 第二輪 |
|---|---|---|
| 群組擁有部門正確 | 79 / 92 | 73 / 92 |
| 群組敏感度正確 | 69 / 92 | 69 / 92 |
| 限制級漏標（最危險） | 1 | 0 |
| 誤標成限制級 | 12 | 17 |
| 隱藏問題抓到 | 3 / 3 | 3 / 3 |
| 一句話寫規則完全正確 | 25 / 30 | 27 / 30 |

同一個模型兩次結果不同，偏向標得更嚴；這正是提案一定要先預覽影響、再由人核准的原因。詳見 [api/eval/AI_REPORT-qwen3.5_9b.md](api/eval/AI_REPORT-qwen3.5_9b.md)（含限制說明；第一輪有一個解析 bug，已修正）。

## 前端（Next.js）

| 頁面 | 給誰 | 內容 |
|---|---|---|
| 我的覆核 | 所有人 | 每個項目是一張鑰匙吊牌：白話說明、期限、保留或撤銷；同儕離群逐個群組決定；決定後蓋章 |
| 覆核活動 | IT | 用最新同步建立活動、依類型看進度、還在等誰、推進時間看提醒與升級、交付執行、下載證據包 |
| 發現 | IT | 依規則分類的所有發現，已核准保留的不列入 |
| 規則 | IT | 一句話寫規則、AI 群組標註、影響預覽、套用與撤回 |
| 查人 | IT | 一個人在 HR、Entra ID（直接與經由哪個群組間接取得）、GitHub、ERP 的所有權限 |

稽核證據包是一個 zip：摘要、每個項目的覆核者（含升級前）與決定理由、例外與到期日、完整事件紀錄、寄出的通知、執行結果，以及當時的 policy.yaml 與它的指紋。

## 執行引擎

`python -m app.execute plan → approve → run → rollback`

- 只自動處理有 API 且能驗證的動作：停用帳號、移出群組、移除管理員角色、刪除來賓、移除 GitHub 成員與外部協作者。ERP 角色、2FA、身分確認、同儕離群一律轉成人工待辦。
- 核准綁定動作內容的指紋，核准後內容被改動就拒絕執行。不可逆的動作（GitHub 移除）核准時必須另外確認。
- 保護清單在執行當下再檢查一次；單次超過 50 筆要加 `--confirm-large`；擔任管理員角色的帳號必須先移除角色才能停用（Graph 本身也會拒絕）。
- 每筆動作先用唯讀 key 讀現況並存成「執行前狀態」，已是目標狀態就不寫；寫入後再用唯讀 key 重新讀取，**寫入回報成功但實際沒生效會被標成驗證失敗**。
- 帳本每一步都原子存檔：中途當掉重跑不會重複寫入。還原依執行前狀態；GitHub 成員只能重新邀請（部分還原），外部協作者無法自動還原。
- 擬真資料端到端：162 筆發現 → 115 筆自動執行並全部驗證 → 重新同步後剩 47 筆，全是人工待辦。

## 真實環境的限制

- GitHub 帳號必須真人註冊，不能批次造假，所以 live 模式只驗證 API 串接，大規模成員資料使用 mock。
- 種子腳本建立的帳號不會自己登入，live 租戶裡只有手動登入過的測試帳號有真實的 `signInActivity`。

## 開發（不用 Docker 跑 API 與前端）

需要 Python 3.12（[uv](https://docs.astral.sh/uv/)）與 Node.js 20 以上。資料庫、收信與 mock 仍用 Docker：

```bash
./setup.sh
docker compose up -d db mailpit mock
set -a; . ./.env; set +a
export DATABASE_URL="postgresql+psycopg://keyward:${POSTGRES_PASSWORD}@127.0.0.1:5438/keyward" SMTP_HOST=127.0.0.1 SMTP_PORT=1027
```

```bash
cd api && uv sync && uv run alembic upgrade head && uv run python -m app.sync && uv run uvicorn app.main:app --port 8390
```

```bash
cd web && npm install && npm run dev      # http://localhost:3500
```

測試不需要資料庫：

```bash
cd api && uv run pytest
```

其他指令（都在 `api/` 底下）：`uv run python -m app.seed.generate`（重新產生擬真資料）、`uv run python -m app.evals.score`（發現規則評測）、`uv run python -m app.evals.ai_eval`（AI 評測，需設定模型）、`uv run python -m app.execute --help`（執行引擎 CLI）。
