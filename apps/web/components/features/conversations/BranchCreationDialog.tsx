"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useCreateBranch } from "@/lib/hooks/use-branch";

const schema = z.object({
  name: z.string().min(1, "Name is required").max(50),
  description: z.string().max(200).optional(),
});

type BranchFormValues = z.infer<typeof schema>;

interface BranchCreationDialogProps {
  conversationId: string;
  messageId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function BranchCreationDialog({
  conversationId,
  messageId,
  onOpenChange,
  open,
}: BranchCreationDialogProps) {
  const createBranch = useCreateBranch();
  const form = useForm<BranchFormValues>({
    defaultValues: { name: "", description: "" },
    resolver: zodResolver(schema),
  });

  const handleSubmit = form.handleSubmit(async (values) => {
    if (!messageId) {
      return;
    }

    await createBranch.mutateAsync({
      conversationId,
      description: values.description,
      name: values.name,
      originating_message_id: messageId,
    });
    form.reset();
    onOpenChange(false);
  });

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogTitle>Create branch</DialogTitle>
        <DialogDescription>
          Fork the conversation from this message to explore a different path.
        </DialogDescription>
        <Form {...form}>
          <form className="space-y-4" onSubmit={handleSubmit}>
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input placeholder="Approach B" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Description</FormLabel>
                  <FormControl>
                    <Input placeholder="Optional context" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button onClick={() => onOpenChange(false)} type="button" variant="ghost">
                Cancel
              </Button>
              <Button type="submit">Create branch</Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
