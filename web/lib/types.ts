export type Me = {
  employee_id: string;
  name: string;
  title: string;
  site: string;
  dept: string;
  is_admin: boolean;
};

export type DemoAccount = {
  employee_id: string;
  name: string;
  title: string;
  site: string;
  role: string;
  pending: number;
  rules: string[];
};

export type Decision = "keep" | "revoke" | "partial";

export type ReviewItem = {
  id: number;
  campaign_id: number;
  rule: string;
  label: string;
  system: string;
  account: string;
  object: string;
  subject_id: string | null;
  subject_name: string | null;
  reviewer_id: string;
  reviewer_name: string;
  explanation: string;
  groups: string[] | null;
  status: "pending" | "decided" | "overdue";
  due_at: string;
  level: number;
  decision: Decision | null;
  reason: string | null;
  decision_detail: { groups?: Record<string, "keep" | "revoke">; keep_until?: string };
  decided_at: string | null;
};

export type Progress = {
  total: number;
  by_status: Record<string, number>;
  by_decision: Record<string, number>;
  escalated: number;
};

export type CampaignSummary = Progress & {
  id: number;
  name: string;
  status: string;
  as_of: string;
  created_at: string;
};

export type CampaignDetail = CampaignSummary & {
  direct: number;
  suppressed: number;
  ledger: string | null;
  execution: Record<string, number> | null;
  by_rule: ({ rule: string; label: string } & Record<string, number | string>)[];
  waiting_on: { employee_id: string; name: string; open: number }[];
};

export type FindingRow = {
  rule: string;
  label: string;
  system: string;
  account: string;
  object: string;
  fix: string;
  employee_id: string | null;
  name: string | null;
  confirmed: boolean;
};

export type Findings = {
  snapshot: string;
  taken_at: string;
  as_of: string;
  suppressed: number;
  items: FindingRow[];
};

export type PersonHit = { employee_id: string; name: string; title: string; site: string; dept: string; status: string };

export type Profile = {
  employee_id: string;
  name: string;
  en_name: string;
  email: string;
  site: string;
  dept: string;
  title: string;
  status: string;
  employment_type: string;
  hire_date: string;
  termination_date: string | null;
  manager: { employee_id: string; name: string } | null;
  transfers: Record<string, string | null>[];
  entra: {
    upn: string;
    enabled: boolean;
    matched_by: string;
    last_sign_in: string | null;
    direct_groups: { name: string; description: string | null }[];
    inherited_groups: { name: string; via: string[] }[];
    roles: string[];
  }[];
  github: { login: string; kind: string; role: string | null; two_factor: boolean | null; matched_by: string; confirmed: boolean }[];
  erp: { role: string; transactions: string[] }[];
  findings: { rule: string; system: string; account: string; object: string; fix: string }[];
};

export type ImpactRow = { rule: string; account: string; object: string; name: string | null };

export type Proposal = {
  id: number;
  source: "classifier" | "sentence";
  kind: "group_label" | "resource" | "sod" | "setting" | "clarify";
  prompt: string;
  target: string;
  proposal: Record<string, unknown>;
  rationale: string | null;
  evidence: string[];
  errors: string[];
  impact: { added: number; removed: number; added_rows: ImpactRow[]; removed_rows: ImpactRow[] } | null;
  model: string | null;
  elapsed_ms: number;
  status: "proposed" | "invalid" | "clarify" | "applied" | "rejected" | "reverted";
  created_at: string;
  decided_by: string | null;
  decided_at: string | null;
};

export type PolicyState = { ai_message: string | null; model: string | null; unlabeled: number; proposals: Proposal[] };
