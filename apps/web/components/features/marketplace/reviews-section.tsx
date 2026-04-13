"use client";

import { useEffect, useMemo, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, PencilLine } from "lucide-react";
import { useForm } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Textarea } from "@/components/ui/textarea";
import {
  ReviewSubmissionSchema,
  type ReviewSubmissionValues,
} from "@/lib/schemas/marketplace";
import {
  useAgentReviews,
  useEditReview,
  useSubmitReview,
} from "@/lib/hooks/use-agent-reviews";
import { useToast } from "@/lib/hooks/use-toast";
import { StarRating } from "@/components/features/marketplace/star-rating";
import { StarRatingInput } from "@/components/features/marketplace/star-rating-input";
import type { AgentReview } from "@/lib/types/marketplace";

export interface ReviewsSectionProps {
  agentFqn: string;
  currentUserReview: AgentReview | null;
}

function mergeReviews(nextReviews: AgentReview[]): AgentReview[] {
  const byId = new Map<string, AgentReview>();

  nextReviews.forEach((review) => {
    byId.set(review.id, review);
  });

  return Array.from(byId.values()).sort((left, right) =>
    right.createdAt.localeCompare(left.createdAt),
  );
}

export function ReviewsSection({
  agentFqn,
  currentUserReview,
}: ReviewsSectionProps) {
  const { toast } = useToast();
  const [page, setPage] = useState(1);
  const [loadedReviews, setLoadedReviews] = useState<AgentReview[]>([]);
  const [isEditing, setIsEditing] = useState(false);
  const reviewsQuery = useAgentReviews(agentFqn, page);
  const submitReview = useSubmitReview(agentFqn);
  const editReview = useEditReview(agentFqn);

  const resolvedCurrentUserReview =
    loadedReviews.find((review) => review.isOwnReview) ?? currentUserReview;

  const form = useForm<ReviewSubmissionValues>({
    resolver: zodResolver(ReviewSubmissionSchema),
    defaultValues: {
      rating: resolvedCurrentUserReview?.rating ?? 5,
      text: resolvedCurrentUserReview?.text ?? "",
    },
  });

  useEffect(() => {
    if (!reviewsQuery.data) {
      return;
    }

    setLoadedReviews((previous) =>
      page === 1
        ? mergeReviews(reviewsQuery.data.items)
        : mergeReviews([...previous, ...reviewsQuery.data.items]),
    );
  }, [page, reviewsQuery.data]);

  useEffect(() => {
    form.reset({
      rating: resolvedCurrentUserReview?.rating ?? 5,
      text: resolvedCurrentUserReview?.text ?? "",
    });
  }, [form, resolvedCurrentUserReview]);

  const reviewCount = reviewsQuery.data?.total ?? loadedReviews.length;
  const averageRating = useMemo(() => {
    if (loadedReviews.length === 0) {
      return null;
    }

    const total = loadedReviews.reduce((sum, review) => sum + review.rating, 0);
    return total / loadedReviews.length;
  }, [loadedReviews]);
  const displayedReviews =
    resolvedCurrentUserReview && !isEditing
      ? loadedReviews.filter((review) => !review.isOwnReview)
      : loadedReviews;

  const handleReset = () => {
    setPage(1);
    setLoadedReviews([]);
  };

  const onSubmit = form.handleSubmit(async (values) => {
    if (resolvedCurrentUserReview && isEditing) {
      await editReview.mutateAsync({
        reviewId: resolvedCurrentUserReview.id,
        payload: values,
      });
      toast({
        title: "Review updated",
        description: "Your review is now reflected in the marketplace.",
        variant: "success",
      });
      setIsEditing(false);
    } else {
      await submitReview.mutateAsync(values);
      toast({
        title: "Review submitted",
        description: "Thanks for sharing feedback with the community.",
        variant: "success",
      });
    }

    handleReset();
  });

  const isMutating = submitReview.isPending || editReview.isPending;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.16em] text-brand-accent">
            Community feedback
          </p>
          <div className="mt-2">
            <StarRating rating={averageRating} reviewCount={reviewCount} size="lg" />
          </div>
        </div>
      </div>

      {loadedReviews.length === 0 && !reviewsQuery.isLoading ? (
        <Card className="border-dashed">
          <CardContent className="p-6 text-sm text-muted-foreground">
            <p className="font-medium text-foreground">No reviews yet</p>
            <p className="mt-2">Be the first to review this agent.</p>
          </CardContent>
        </Card>
      ) : null}

      {resolvedCurrentUserReview && !isEditing ? (
        <Card>
          <CardContent className="space-y-3 p-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="font-medium">Your review</p>
                <StarRating rating={resolvedCurrentUserReview.rating} size="sm" />
              </div>
              <Button size="sm" variant="outline" onClick={() => setIsEditing(true)}>
                <PencilLine className="h-4 w-4" />
                Edit
              </Button>
            </div>
            {resolvedCurrentUserReview.text ? (
              <p className="text-sm text-muted-foreground">
                {resolvedCurrentUserReview.text}
              </p>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {(!resolvedCurrentUserReview || isEditing) ? (
        <Card>
          <CardContent className="p-5">
            <Form {...form}>
              <form className="space-y-4" onSubmit={onSubmit}>
                <FormField
                  control={form.control}
                  name="rating"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Rating</FormLabel>
                      <FormControl>
                        <StarRatingInput
                          name="Rating"
                          value={field.value}
                          onChange={field.onChange}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="text"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Review</FormLabel>
                      <FormControl>
                        <Textarea
                          maxLength={2000}
                          placeholder="Share what worked well and where this agent needs improvement."
                          {...field}
                          value={field.value ?? ""}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <div className="flex items-center gap-2">
                  <Button disabled={isMutating} type="submit">
                    {isMutating ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Saving
                      </>
                    ) : resolvedCurrentUserReview ? (
                      "Save review"
                    ) : (
                      "Submit review"
                    )}
                  </Button>
                  {resolvedCurrentUserReview && isEditing ? (
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => {
                        setIsEditing(false);
                        form.reset({
                          rating: resolvedCurrentUserReview.rating,
                          text: resolvedCurrentUserReview.text ?? "",
                        });
                      }}
                    >
                      Cancel
                    </Button>
                  ) : null}
                </div>
              </form>
            </Form>
          </CardContent>
        </Card>
      ) : null}

      <div className="space-y-3">
        {displayedReviews.map((review) => (
          <Card key={review.id}>
            <CardContent className="space-y-3 p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="font-medium">{review.authorName}</p>
                  <p className="text-sm text-muted-foreground">
                    {new Date(review.updatedAt ?? review.createdAt).toLocaleDateString()}
                  </p>
                </div>
                <StarRating rating={review.rating} size="sm" />
              </div>
              {review.text ? (
                <p className="text-sm text-muted-foreground">{review.text}</p>
              ) : (
                <p className="text-sm italic text-muted-foreground">
                  No written feedback provided.
                </p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {reviewsQuery.data?.hasNext ? (
        <Button
          disabled={reviewsQuery.isFetching}
          variant="outline"
          onClick={() => setPage((currentPage) => currentPage + 1)}
        >
          {reviewsQuery.isFetching ? "Loading more…" : "Load more reviews"}
        </Button>
      ) : null}
    </div>
  );
}
