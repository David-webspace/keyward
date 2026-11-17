const SITE: Record<string, string> = {
  TPE: "台北總部", TYN: "桃園廠", HSC: "新竹研發", DGN: "東莞廠", BNH: "越南北寧", CBI: "泰國春武里",
  SJC: "聖荷西", TYO: "東京", MUC: "慕尼黑",
};

export const site = (code: string) => SITE[code] ?? code;

const DEPT: Record<string, string> = {
  EXEC: "經營管理", FIN: "財務", LEGAL: "法務", HR: "人資", IT: "資訊", SALES: "業務", FAE: "應用工程", RDHW: "硬體研發",
  RDFW: "韌體研發", TEST: "測試工程", MFG: "製造", QA: "品保", SC: "供應鏈", WH: "倉儲物流",
};

export const dept = (code: string) => DEPT[code] ?? code;

// 後端存 UTC（不帶時區），顯示成台北時間的日期
export function day(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  return d.toLocaleDateString("zh-TW", { timeZone: "Asia/Taipei", year: "numeric", month: "2-digit", day: "2-digit" });
}

export function dateTime(iso: string): string {
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  return d.toLocaleString("zh-TW", { timeZone: "Asia/Taipei", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });
}

export const DECISION_LABEL = { keep: "保留", revoke: "撤銷", partial: "部分撤銷" } as const;

// 外部來賓的 UPN 長這樣：james.davis_kestrel-audit.example#EXT#@arcwell.example，顯示時還原成對方原本的 Email
export function account(upn: string): string {
  if (!upn.includes("#EXT#")) return upn;
  return upn.split("#EXT#")[0].replace(/_([^_]+)$/, "@$1");
}
