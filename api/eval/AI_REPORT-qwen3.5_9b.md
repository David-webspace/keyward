# AI 規則提案評測（qwen3.5:9b）

模型只產生提案；所有提案都經程式驗證，並由 IT 核准後才生效。

## 群組標註

- 群組數：92；未通過驗證（代碼錯誤或引用了輸入裡沒有的依據）：13
- 擁有部門正確：73 / 92
- 敏感度正確：69 / 92
- 限制級群組：標出 7 / 8；**漏標（最危險）：無**
- 把非限制級標成限制級（會多出需要覆核的項目）：APP-CRM, APP-EDA-Licenses, EXT-Auditors, EXT-Customer-Portal, EXT-Firmware-Partners, Legacy-Lotus-Migration, PRJ-Atlas-Tariff-Impact, PRJ-Falcon-8D-Customer-Returns, PRJ-Glacier-Zero-Trust-Network, PRJ-Helix-LED-Driver-Gen4, PRJ-Juniper-Fan-Control, PRJ-Kestrel-IATF-Audit-2026, PRJ-Nimbus-Supplier-Quality-Scorecard, PRJ-Orion-CBI-Hiring-Wave, PRJ-Orion-Telemetry-Agent, PRJ-Quartz-OTA-Update, Training-Safety-TYN
- 套用所有限制級建議後：隱藏問題抓到 3 / 3，另外多出 34 筆發現
- 平均每個群組 10.1 秒

| 群組 | 應為 | 模型 | 驗證 |
|---|---|---|---|
| APP-Admin-Portal | restricted / IT | restricted / IT ✓ | 通過 |
| APP-CRM | internal / SALES | restricted / SALES ✗ | 通過 |
| APP-EDA-Licenses | internal / RDHW | restricted / IT ✗ | 通過 |
| APP-ERP-Users | internal / IT | internal / IT ✓ | 引用的依據「App-ERP-Users」沒有出現在輸入中 |
| APP-PLM | internal / RDHW | internal / IT ✗ | 通過 |
| APP-VPN | general / IT | internal / IT ✗ | 通過 |
| Club-Hsinchu-Running | general / HR | general / IT ✗ | 通過 |
| Club-Taipei-Badminton | general / HR | general / TPE ✗ | 擁有部門 TPE 不存在 |
| Committee-ESG | internal / EXEC | internal / EXEC ✓ | 通過 |
| Committee-Welfare | general / HR | general / IT ✗ | 通過 |
| DL-All-Arcwell | general / HR | general / IT ✗ | 通過 |
| EXT-Auditors | internal / QA | restricted / LEGAL ✗ | 沒有指定可以存取的部門；限制級群組的存取對象必須包含擁有部門 |
| EXT-Customer-Portal | internal / SALES | restricted / IT ✗ | 沒有指定可以存取的部門；限制級群組的存取對象必須包含擁有部門 |
| EXT-Firmware-Partners | internal / RDFW | restricted / RDFW ✗ | 通過 |
| EXT-Logistics-Partners | internal / WH | internal / SC ✗ | 通過 |
| Legacy-Lotus-Migration | general / IT | restricted / TEST ✗ | 通過 |
| M365-Copilot-Pilot | internal / IT | internal / IT ✓ | 通過 |
| Old-SharePoint-Owners | general / IT | general / IT ✓ | 通過 |
| PRJ-Atlas-ERP-S4-Readiness | internal / IT | internal / IT ✓ | 通過 |
| PRJ-Atlas-GaN-Charger-140W | internal / RDHW | internal / RDHW ✓ | 通過 |
| PRJ-Atlas-Medical-PSU | internal / RDHW | internal / RDHW ✓ | 通過 |
| PRJ-Atlas-Tariff-Impact | internal / SC | restricted / SC ✗ | 通過 |
| PRJ-Aurora-VMI-Pilot | internal / SC | internal / SC ✓ | 通過 |
| PRJ-Aurora-Yield-Taskforce | internal / MFG | internal / MFG ✓ | 通過 |
| PRJ-Beacon-AOI-Rollout | internal / MFG | internal / MFG ✓ | 引用的依據「」沒有出現在輸入中 |
| PRJ-Beacon-Budget-2027 | restricted / FIN | restricted / FIN ✓ | 通過 |
| PRJ-Beacon-Laptop-Refresh-2026 | internal / IT | internal / IT ✓ | 通過 |
| PRJ-Beacon-Secure-Boot | internal / RDFW | internal / RDFW ✓ | 通過 |
| PRJ-Cobalt-Dual-Sourcing-2026 | internal / SC | internal / SC ✓ | 通過 |
| PRJ-Cobalt-M365-Migration | internal / IT | internal / IT ✓ | 通過 |
| PRJ-Cobalt-Trade-Show-APEC | internal / SALES | internal / SALES ✓ | 通過 |
| PRJ-Comet-Reference-Design-Kit | internal / FAE | internal / FAE ✓ | 通過 |
| PRJ-Comet-WMS-Barcode | internal / WH | internal / SC ✗ | 通過 |
| PRJ-Ember-ATE-Migration | internal / TEST | internal / TEST ✓ | 通過 |
| PRJ-Ember-Talent-Review-2026 | restricted / HR | restricted / HR ✓ | 沒有指定可以存取的部門；限制級群組的存取對象必須包含擁有部門 |
| PRJ-Falcon-8D-Customer-Returns | internal / QA | restricted / QA ✗ | 通過 |
| PRJ-Falcon-EV-OBC-11kW | internal / RDHW | internal / RDHW ✓ | 引用的依據「成员部門分布：RDHW 1」沒有出現在輸入中 |
| PRJ-Falcon-PMBus-Stack | internal / RDFW | internal / RDFW ✓ | 通過 |
| PRJ-Glacier-Pricing-Review-2027 | restricted / SALES | restricted / FIN ✗ | 通過 |
| PRJ-Glacier-Test-Data-Lake | internal / TEST | internal / TEST ✓ | 通過 |
| PRJ-Glacier-Zero-Trust-Network | internal / IT | restricted / IT ✗ | 通過 |
| PRJ-Harbor-Calibration-Tool | internal / RDFW | internal / RDFW ✓ | 通過 |
| PRJ-Harbor-ISO14001-Renewal | internal / QA | general / QA ✗ | 通過 |
| PRJ-Harbor-Lean-TYN-2026 | internal / MFG | internal / MFG ✓ | 通過 |
| PRJ-Helix-Audit-FY2025 | restricted / FIN | restricted / FIN ✓ | 通過 |
| PRJ-Helix-Bootloader-v3 | internal / RDFW | internal / RDFW ✓ | 通過 |
| PRJ-Helix-LED-Driver-Gen4 | internal / RDHW | restricted / RDHW ✗ | 通過 |
| PRJ-Helix-Transfer-Pricing | restricted / FIN | restricted / FIN ✓ | 通過 |
| PRJ-Juniper-Customer-Lab-Tours | internal / FAE | internal / FAE ✓ | 通過 |
| PRJ-Juniper-Fan-Control | internal / RDFW | restricted / RDFW ✗ | 通過 |
| PRJ-Juniper-PSU-650W | internal / RDHW | internal / RDHW ✓ | 通過 |
| PRJ-Kestrel-EU-Distributor-Onboarding | internal / SALES | internal / SALES ✓ | 通過 |
| PRJ-Kestrel-Fixture-Library | internal / TEST | internal / TEST ✓ | 通過 |
| PRJ-Kestrel-IATF-Audit-2026 | internal / QA | restricted / QA ✗ | 通過 |
| PRJ-Lumen-CBI-Line-Ramp | internal / MFG | internal / MFG ✓ | 通過 |
| PRJ-Lumen-Design-In-Support | internal / FAE | general / IT ✗ | 通過 |
| PRJ-Lumen-SMT-Line-Upgrade | internal / MFG | internal / MFG ✓ | 通過 |
| PRJ-Nimbus-CRM-Cleanup | internal / SALES | internal / SALES ✓ | 通過 |
| PRJ-Nimbus-Reliability-Lab | internal / QA | internal / QA ✓ | 通過 |
| PRJ-Nimbus-Supplier-Quality-Scorecard | internal / QA | restricted / QA ✗ | 引用的依據「成員名稱：PRJ-Nimbus-Supplier-Quality-Scorecard」沒有出現在輸入中 |
| PRJ-Orion-Adapter-USB-PD | internal / RDHW | internal / RDHW ✓ | 通過 |
| PRJ-Orion-CBI-Hiring-Wave | internal / HR | restricted / HR ✗ | 通過 |
| PRJ-Orion-Telemetry-Agent | internal / RDFW | restricted / RDFW ✗ | 通過 |
| PRJ-Quartz-Burn-in-Automation | internal / TEST | internal / TEST ✓ | 通過 |
| PRJ-Quartz-OTA-Update | internal / RDFW | restricted / RDFW ✗ | 通過 |
| PRJ-Quartz-Supplier-Portal | internal / SC | internal / SC ✓ | 通過 |
| PRJ-Sierra-Japan-Auto-Tier1 | internal / SALES | internal / SALES ✓ | 通過 |
| PRJ-Sierra-Key-Account-Hyperscaler | internal / SALES | internal / SALES ✓ | 通過 |
| PRJ-Sierra-MES-Upgrade | internal / IT | internal / IT ✓ | 通過 |
| PRJ-Titan-HiPot-Station | internal / TEST | internal / TEST ✓ | 通過 |
| PRJ-Titan-Server-PSU-3kW | internal / RDHW | internal / RDHW ✓ | 通過 |
| PRJ-Titan-Warehouse-Layout-TYN | internal / WH | internal / WH ✓ | 通過 |
| PRJ-Vega-DC-DC-Brick | internal / RDHW | internal / RDHW ✓ | 引用的依據「」沒有出現在輸入中 |
| PRJ-Vega-Solar-Microinverter | internal / RDHW | internal / RDHW ✓ | 通過 |
| PRJ-Vega-Telecom-Rectifier | internal / RDHW | internal / RDHW ✓ | 引用的依據「["名稱 PRJ-Vega-Telecom-Rectifier 中的 'PRJ' 表示專案",'說明欄位提及 '硬體研發專案：Telecom-Rec |
| PRJ-Zephyr-Digital-Control-Loop | internal / RDFW | internal / RDFW ✓ | 通過 |
| PRJ-Zephyr-Export-Control-Review | restricted / LEGAL | restricted / LEGAL ✓ | 通過 |
| PRJ-Zephyr-Kaizen-DGN | internal / MFG | internal / MFG ✓ | 通過 |
| SG-Intern-2026 | internal / HR | general / SALES ✗ | 通過 |
| SG-Kiosk-Devices | internal / IT | general / IT ✗ | 通過 |
| SG-Laptop-Pilot | internal / IT | internal / IT ✓ | 通過 |
| SG-Mobile-Devices | internal / IT | internal / IT ✓ | 引用的依據「群組名稱為'SG-Mobile-Devices'」沒有出現在輸入中；引用的依據「說明為'公務手機'」沒有出現在輸入中 |
| SG-Printers-HSC | general / IT | general / IT ✓ | 引用的依據「名稱中的'HSC'指向新竹研發中心」沒有出現在輸入中；引用的依據「說明為'新竹印表機'」沒有出現在輸入中 |
| SG-Printers-TPE | general / IT | general / IT ✓ | 通過 |
| SG-Remote-Workers | internal / IT | internal / IT ✓ | 引用的依據「群組名稱: SG-Singapore-Remote-Workers」沒有出現在輸入中 |
| SG-Visitors-TPE | general / HR | internal / IT ✗ | 通過 |
| TMP-CBI-Launch | internal / MFG | internal / MFG ✓ | 通過 |
| Temp-Audit-2025 | restricted / FIN | restricted / IT ✗ | 通過 |
| Test-Group-1 | general / IT | general / TEST ✗ | 通過 |
| Test-Group-2 | general / IT | general / TEST ✗ | 通過 |
| Training-ISO27001-2026 | internal / IT | internal / IT ✓ | 通過 |
| Training-Safety-TYN | internal / MFG | restricted / IT ✗ | 通過 |

## 一句話寫規則

- 完全正確：27 / 30（平均 6.6 秒）
- 該反問卻自己猜：0

| 類型 | 句數 | 正確 |
|---|---:|---:|
| resource | 12 | 11 |
| sod | 7 | 6 |
| setting | 5 | 5 |
| clarify | 6 | 5 |

| 句子 | 結果 | 模型轉出 |
|---|---|---|
| 薪資資料只有台北的人資和財務能看 | ✓ | {"action": "resource", "group": "RES-Payroll", "departments": ["FIN", "HR"], "sites": ["TPE"]} |
| 董事會資料只限經營管理部門存取 | ✓ | {"action": "resource", "group": "RES-Board-Materials", "departments": ["EXEC"], "sites": []} |
| 人事檔案只有人資可以看 | ✓ | {"action": "resource", "group": "RES-HR-Records", "departments": ["HR"], "sites": []} |
| 供應商合約只開放給供應鏈、法務和財務 | ✓ | {"action": "resource", "group": "RES-Supplier-Contracts", "departments": ["FIN", "LEGAL", "SC"], "sites": []} |
| 2027 年預算專案只有財務和經營管理可以參與 | ✓ | {"action": "resource", "group": "PRJ-Beacon-Budget-2027", "departments": ["EXEC", "FIN"], "sites": []} |
| 移轉訂價專案限財務部 | ✓ | {"action": "resource", "group": "PRJ-Helix-Transfer-Pricing", "departments": ["FIN"], "sites": []} |
| 2027 定價檢討專案只限業務和財務 | ✗ | {"action": "clarify"} |
| 2026 人才盤點專案只有人資和經營管理能看 | ✓ | {"action": "resource", "group": "PRJ-Ember-Talent-Review-2026", "departments": ["EXEC", "HR"], "sites": []} |
| 出口管制審查專案只限法務 | ✓ | {"action": "resource", "group": "PRJ-Zephyr-Export-Control-Review", "departments": ["LEGAL"], "sites": []} |
| IT 管理入口只能給資訊部 | ✓ | {"action": "resource", "group": "APP-Admin-Portal", "departments": ["IT"], "sites": []} |
| 財務 Power BI 報表只有財務能看 | ✓ | {"action": "resource", "group": "APP-PowerBI-Finance", "departments": ["FIN"], "sites": []} |
| 桃園廠的 MES 只開放給桃園廠的製造和品保 | ✓ | {"action": "resource", "group": "APP-MES-TYN", "departments": ["MFG", "QA"], "sites": ["TYN"]} |
| 同一個人不能同時建立銷售訂單又開立銷貨折讓 | ✓ | {"action": "sod", "pair": ["CREDIT_MEMO", "SO_CREATE"]} |
| 開工單的人不能自己做生產報工 | ✓ | {"action": "sod", "pair": ["PROD_CONFIRM", "PROD_ORDER"]} |
| 負責收貨的人不可以同時做庫存調整 | ✗ | {"action": "clarify"}；模型沒有回傳結構化結果 |
| 維護料號主檔和維護 BOM 不能是同一個人 | ✓ | {"action": "sod", "pair": ["BOM_MAINT", "MAT_MAINT"]} |
| 總帳過帳和月結關帳要由不同人負責 | ✓ | {"action": "sod", "pair": ["GL_CLOSE", "GL_POST"]} |
| 品質凍結和品質放行不能由同一人執行 | ✓ | {"action": "sod", "pair": ["QC_BLOCK", "QC_RELEASE"]} |
| 能維護價格的人不准核准銷售訂單 | ✓ | {"action": "sod", "pair": ["PRICE_MAINT", "SO_APPROVE"]} |
| 超過 60 天沒登入就算殭屍帳號 | ✓ | {"action": "setting", "key": "inactivity_days", "value": 60} |
| 新帳號給 14 天的寬限期 | ✓ | {"action": "setting", "key": "new_account_grace_days", "value": 14} |
| 轉調後舊權限最多保留 15 天 | ✓ | {"action": "setting", "key": "transfer_grace_days", "value": 15} |
| 閒置帳號的標準改成 120 天 | ✓ | {"action": "setting", "key": "inactivity_days", "value": 120} |
| 45 天未登入即視為長期未登入 | ✓ | {"action": "setting", "key": "inactivity_days", "value": 45} |
| 那個專案的資料要管嚴一點 | ✓ | {"action": "clarify"} |
| 薪水相關的東西要限制 | ✓ | {"action": "clarify"} |
| 客戶資料只有業務能看 | ✓ | {"action": "clarify"} |
| 限制 Slack 頻道的存取 | ✓ | {"action": "clarify"} |
| 每個人的密碼要 90 天換一次 | ✗ | {"action": "clarify"}；模型沒有回傳結構化結果 |
| 研發專案只有研發可以看 | ✓ | {"action": "clarify"} |

## 解讀與限制

- **設定**：本機 Ollama `qwen3.5:9b`，`reasoning_effort=none`。開啟思考時一次要 40 秒左右，還常常沒有回傳工具呼叫；關掉後一次約 10 秒，品質反而較穩定。
- **同一個模型，兩次結果不同**。第一輪（當時有一個解析 bug：模型把依據清單整個當成一段文字回傳時，程式會把它逐字拆開；已修正）的結果：擁有部門 79/92、敏感度 69/92、漏標限制級 1 個（Temp-Audit-2025）、誤標成限制級 12 個、一句話寫規則 25/30。第二輪（本報告）：擁有部門 73/92、漏標 0、誤標 17、一句話寫規則 27/30。瀏覽器實測時，同一個 APP-PLM 一次被判成「內部」，另一次被判成「只有資訊部能存取」，影響預覽顯示套用後會多出 188 筆發現。**模型的建議不穩定，所以一定要先預覽影響、再由人核准。**
- **誤判的方向**：模型偏向把群組標得更嚴（誤標成限制級 12–17 個），很少放過真正的限制級（漏標 0–1 個）。對權限盤點來說，這個方向比較安全，代價是 IT 要捨棄比較多提案。
- **驗證擋下的**：捏造的群組名稱（把「人才盤點專案」編成不存在的名稱）、被改寫或改成簡體字的引用、限制級卻沒有填存取對象。
- **驗證擋不下的**：格式合法但語意不對的規則，例如「桃園廠的 MES 只開放給桃園廠的製造和品保」，模型曾漏掉據點限制，讓規則範圍比要求的大。這只能靠人在影響預覽時發現。
- **「沒有回傳結構化結果」**的句子（例如密碼期限，本來就不支援）會被當成反問，不會產生任何規則，所以計為錯誤但不會造成傷害。
- **評測資料的限制**：群組的標準答案和 30 句測試句都是我寫的；測試句有些和提示裡的範例句型相近，數字可能偏樂觀。標準答案也只是一種合理的判斷，例如「EXT-Auditors（外部稽核人員）」算內部還是限制級，本來就有討論空間。
- 只用本機模型評測，沒有花模型費用；尚未用 Claude Haiku／Sonnet 對照。
