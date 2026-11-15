import { Suspense } from "react";
import Workspace from "@/components/Workspace";

export default function Page() {
  return (
    <Suspense fallback={<div className="flex h-screen items-center justify-center muted">Loading Vid2Graph…</div>}>
      <Workspace />
    </Suspense>
  );
}
