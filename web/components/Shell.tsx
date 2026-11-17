import { TopBar } from "./TopBar";

export function Shell({ title, lead, children }: { title: string; lead?: React.ReactNode; children: React.ReactNode }) {
  return (
    <>
      <TopBar />
      <main className="mx-auto max-w-6xl px-4 py-8">
        <h1 className="text-2xl font-semibold break-words">{title}</h1>
        {lead && <div className="mt-2 max-w-3xl text-muted break-words">{lead}</div>}
        <div className="mt-6">{children}</div>
      </main>
    </>
  );
}
