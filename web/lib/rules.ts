import { dept, site } from "./format";
import type { Proposal } from "./types";

export const SENSITIVITY = { restricted: "限制級", internal: "內部", general: "一般" } as Record<string, string>;
const SETTING = {
  inactivity_days: "幾天沒登入算殭屍帳號", new_account_grace_days: "新帳號寬限天數", transfer_grace_days: "轉調寬限天數",
} as Record<string, string>;

type Audience = { departments?: string[]; sites?: string[] };

function who(a: Audience): string {
  const d = (a.departments ?? []).map(dept).join("、") || "（未指定部門）";
  return a.sites?.length ? `${a.sites.map(site).join("、")}的${d}` : d;
}

// 把提案寫成一句人看得懂的話
export function describe(p: Proposal): string {
  const x = p.proposal as Record<string, unknown> & Audience;
  switch (p.kind) {
    case "group_label": {
      const s = `${SENSITIVITY[x.sensitivity as string] ?? x.sensitivity}・擁有部門 ${dept(String(x.owner_dept))}`;
      return x.sensitivity === "restricted" ? `${s}・只有${who(x.audience as Audience)}可以存取` : s;
    }
    case "resource":
      return `${x.group} 只有${who(x)}可以存取`;
    case "sod":
      return `職責分離：${x.zh}（${x.left} × ${x.right}）`;
    case "setting":
      return `${SETTING[x.key as string] ?? x.key} 改為 ${x.value} 天`;
    default:
      return `需要補充說明：${x.question ?? ""}`;
  }
}
