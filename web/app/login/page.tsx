"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [restaurantName, setRestaurantName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      if (data.session) router.replace("/");
    });
  }, [router]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setPending(true);
    try {
      if (mode === "signup") {
        const { data, error: signUpError } = await supabase.auth.signUp({
          email: email.trim(),
          password,
          options: { data: { restaurant_name: restaurantName.trim() || "My Restaurant" } },
        });
        if (signUpError) throw signUpError;
        if (!data.session) {
          setNotice("Check your email to confirm the account, then sign in.");
          setMode("signin");
          return;
        }
      } else {
        const { error: signInError } = await supabase.auth.signInWithPassword({
          email: email.trim(),
          password,
        });
        if (signInError) throw signInError;
      }
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="flex min-h-dvh flex-col justify-center px-5 py-10">
      <p className="text-3xl font-semibold tracking-tight">PlateCost</p>
      <p className="mt-2 text-muted">Photograph a receipt. PlateCost files the expense.</p>

      <form onSubmit={submit} className="mt-8 space-y-3">
        {mode === "signup" ? (
          <label className="block text-sm">
            Restaurant name
            <input
              value={restaurantName}
              onChange={(event) => setRestaurantName(event.target.value)}
              className="mt-1 h-12 w-full rounded-xl border border-line bg-card px-3"
              autoComplete="organization"
            />
          </label>
        ) : null}
        <label className="block text-sm">
          Email
          <input
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="mt-1 h-12 w-full rounded-xl border border-line bg-card px-3"
            autoComplete="email"
          />
        </label>
        <label className="block text-sm">
          Password
          <input
            type="password"
            required
            minLength={6}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="mt-1 h-12 w-full rounded-xl border border-line bg-card px-3"
            autoComplete={mode === "signup" ? "new-password" : "current-password"}
          />
        </label>
        {error ? <p className="text-sm text-danger">{error}</p> : null}
        {notice ? <p className="text-sm text-muted">{notice}</p> : null}
        <button
          type="submit"
          disabled={pending}
          className="h-14 w-full rounded-full bg-accent font-semibold text-white disabled:opacity-60"
        >
          {pending ? "Please wait…" : mode === "signup" ? "Create account" : "Sign in"}
        </button>
      </form>

      <button
        type="button"
        onClick={() => {
          setMode(mode === "signup" ? "signin" : "signup");
          setError(null);
          setNotice(null);
        }}
        className="mt-6 text-sm text-muted"
      >
        {mode === "signup" ? "Already have an account? Sign in" : "New restaurant? Create an account"}
      </button>
    </main>
  );
}
