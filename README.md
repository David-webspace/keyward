# keyward

跨平台帳號權限盤點助理：以 Microsoft Entra ID 為身分主軸，對照 HR 名冊，找出離職未停用、轉調未收回、過期來賓、殭屍帳號、權限過大、職責分離衝突，經主管覆核後安全地撤銷，並留下稽核證據。

> 開發中。目前完成：擬真資料產生器、Microsoft Graph 與 GitHub 的 mock、同步程式（delta 增量）、身分對應、發現規則、評測、執行引擎（核准、冪等執行、驗證、還原）、覆核流程（分派、提醒、升級、例外、交付執行）、前端工作台、稽核證據包。

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

## 前端（Next.js）

| 頁面 | 給誰 | 內容 |
|---|---|---|
| 我的覆核 | 所有人 | 每個項目是一張鑰匙吊牌：白話說明、期限、保留或撤銷；同儕離群逐個群組決定；決定後蓋章 |
| 覆核活動 | IT | 用最新同步建立活動、依類型看進度、還在等誰、推進時間看提醒與升級、交付執行、下載證據包 |
| 發現 | IT | 依規則分類的所有發現，已核准保留的不列入 |
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

## 執行

```bash
cd api
uv sync
uv run python -m app.seed.generate   # 產生 data/synthetic/
uv run pytest
```

啟動 mock：

```bash
./setup.sh                            # 產生 .env（隨機的 mock 憑證）
set -a; . ./.env; set +a
cd api && uv run uvicorn app.mock.main:default_app --factory --port 8391
```

前端：

```bash
cd web && npm install && npm run dev   # http://localhost:3500，API 預設連 http://127.0.0.1:8390
```

或使用 Docker：`./setup.sh && docker compose up -d --build`（PostgreSQL、覆核 API、前端、mock、Mailpit）。

> Docker 映像建置尚未驗證：開發機的 Docker 目前拉不到基礎映像。覆核 API 已在本機對 PostgreSQL 16 與 Mailpit 實測。
