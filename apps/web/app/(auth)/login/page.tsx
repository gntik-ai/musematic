"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowRight, ShieldCheck, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { mockTokenPair, mockUser, workspaces } from "@/mocks/handlers";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState(mockUser.email);
  const [password, setPassword] = useState("demo-password");
  const setTokens = useAuthStore((state) => state.setTokens);
  const setUser = useAuthStore((state) => state.setUser);
  const setWorkspaceList = useWorkspaceStore((state) => state.setWorkspaceList);
  const setCurrentWorkspace = useWorkspaceStore((state) => state.setCurrentWorkspace);

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    setTokens(mockTokenPair);
    setUser({
      ...mockUser,
      email,
    });
    setWorkspaceList(workspaces);
    setCurrentWorkspace(workspaces[0]);
    router.replace("/");
  };

  return (
    <Card className="border-brand-primary/20 bg-card/90 backdrop-blur">
      <CardHeader className="space-y-4">
        <div className="flex items-center gap-3 text-brand-primary">
          <div className="rounded-full bg-brand-primary/12 p-3">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div className="rounded-full border border-brand-accent/30 bg-brand-accent/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">
            Control Surface
          </div>
        </div>
        <div>
          <CardTitle className="text-3xl">Sign in to Musematic</CardTitle>
          <CardDescription className="mt-2 text-base">
            This scaffold uses a mock login by default so the shell, stores, and live UI behaviors can be exercised immediately.
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <form className="space-y-5" onSubmit={handleSubmit}>
          <label className="block space-y-2">
            <span className="text-sm font-medium">Email</span>
            <Input value={email} onChange={(event) => setEmail(event.target.value)} />
          </label>
          <label className="block space-y-2">
            <span className="text-sm font-medium">Password</span>
            <Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
          </label>
          <Button className="w-full justify-between" type="submit">
            Continue with mock workspace
            <ArrowRight className="h-4 w-4" />
          </Button>
        </form>
        <div className="mt-6 rounded-xl border border-border/70 bg-muted/40 p-4 text-sm text-muted-foreground">
          <div className="mb-2 flex items-center gap-2 font-medium text-foreground">
            <Sparkles className="h-4 w-4 text-brand-accent" />
            Development shortcut
          </div>
          Any credentials work in the scaffold. The page seeds a default user profile, tokens, and workspace list so the app shell is immediately usable.
        </div>
      </CardContent>
    </Card>
  );
}
