"use client";

import { useState } from "react";
import { PostButton } from "@/components/PostButton";

// 示範用：把時間推到指定日期，跑一次提醒與升級
export function TickForm({ id }: { id: number }) {
  const [at, setAt] = useState("");
  return (
    <div className="flex flex-wrap items-start gap-2">
      <input type="date" value={at} onChange={(e) => setAt(e.target.value)} aria-label="模擬日期"
        className="num rounded-sm border border-rule bg-white px-2 py-1.5 text-sm" />
      <PostButton url={`/api/campaigns/${id}/tick`} body={at ? { now: `${at}T09:00:00` } : {}}
        label={at ? "推到這天，寄提醒與升級" : "現在檢查提醒與升級"} busyLabel="檢查中…"
        done="提醒 {reminded} 項、升級 {escalated} 項、逾期轉資安 {overdue} 項" />
    </div>
  );
}
