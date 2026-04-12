import { Skeleton } from "@/components/ui/skeleton";

export default function ConversationLoadingPage() {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {Array.from({ length: 3 }, (_, index) => (
          <Skeleton className="h-10 w-32" key={`tab-skeleton-${index}`} />
        ))}
      </div>
      <Skeleton className="h-16 w-full" />
      <div className="space-y-3">
        {Array.from({ length: 5 }, (_, index) => (
          <Skeleton className="h-24 w-full" key={`message-skeleton-${index}`} />
        ))}
      </div>
    </div>
  );
}
