import { Compass } from "lucide-react";
import { ButtonLink, EmptyState } from "../../components/ui";
import { useDocumentTitle } from "../../lib/hooks";

export function NotFoundPage() {
  useDocumentTitle("Not found");
  return (
    <div className="mx-auto max-w-xl py-16">
      <EmptyState
        icon={<Compass className="size-8" />}
        title="Page not found"
        action={
          <ButtonLink to="/" variant="primary">
            Go to dashboard
          </ButtonLink>
        }
      >
        The address doesn't match any page. Try the search (Ctrl+K) or the curriculum map.
      </EmptyState>
    </div>
  );
}
