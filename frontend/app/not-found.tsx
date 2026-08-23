import Link from "next/link";

import { Button } from "@/components/ui/button";

/** Shown for any unknown route. The app has exactly one real page. */
export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-[60vh] max-w-md flex-col items-center justify-center gap-4 px-4 text-center">
      <div className="space-y-2">
        <h1 className="text-xl font-semibold">Page not found</h1>
        <p className="text-muted-foreground text-sm">
          That page does not exist. The analyzer lives on the home page.
        </p>
      </div>

      <Button asChild>
        <Link href="/">Back to the analyzer</Link>
      </Button>
    </main>
  );
}
