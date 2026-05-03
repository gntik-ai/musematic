"use client";

import { useState } from "react";
import { Loader2, Plus } from "lucide-react";
import type { SubProcessorCreate } from "@/lib/api/data-lifecycle";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAddSubProcessor } from "@/lib/hooks/use-data-lifecycle";

export function AddSubProcessorDialog() {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [location, setLocation] = useState("");
  const [dataCategories, setDataCategories] = useState("");
  const [privacyPolicyUrl, setPrivacyPolicyUrl] = useState("");
  const add = useAddSubProcessor();

  const reset = () => {
    setName("");
    setCategory("");
    setLocation("");
    setDataCategories("");
    setPrivacyPolicyUrl("");
  };

  const handleSubmit = () => {
    const payload: SubProcessorCreate = {
      name: name.trim(),
      category: category.trim(),
      location: location.trim(),
      data_categories: dataCategories
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    };
    const trimmedPrivacy = privacyPolicyUrl.trim();
    if (trimmedPrivacy) payload.privacy_policy_url = trimmedPrivacy;
    add.mutate(payload,
      {
        onSuccess: () => {
          reset();
          setOpen(false);
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="mr-2 h-4 w-4" />
          Add sub-processor
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add sub-processor</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 text-sm">
          <div className="space-y-1">
            <Label htmlFor="sp-name">Name</Label>
            <Input id="sp-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="sp-category">Category</Label>
            <Input
              id="sp-category"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              placeholder="LLM provider, infrastructure, billing…"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="sp-location">Location</Label>
            <Input
              id="sp-location"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="USA, Germany, Ireland…"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="sp-categories">Data categories (comma-separated)</Label>
            <Input
              id="sp-categories"
              value={dataCategories}
              onChange={(e) => setDataCategories(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="sp-privacy">Privacy policy URL</Label>
            <Input
              id="sp-privacy"
              value={privacyPolicyUrl}
              onChange={(e) => setPrivacyPolicyUrl(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!name || !category || add.isPending}>
            {add.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Add
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
