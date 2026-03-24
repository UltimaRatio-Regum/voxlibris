import { useState, useEffect } from "react";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { useToast } from "@/hooks/use-toast";
import logoHorizontal from "@assets/tomevox_logo_horizontal.png";

interface LoginPageProps {
  onShowRegister: () => void;
}

export function LoginPage({ onShowRegister }: LoginPageProps) {
  const { login } = useAuth();
  const { toast } = useToast();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [registrationMode, setRegistrationMode] = useState<string>("disabled");

  useEffect(() => {
    fetch("/api/auth/registration-mode")
      .then((r) => r.json())
      .then((d) => setRegistrationMode(d.mode))
      .catch(() => {});
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await login(username, password);
    } catch (err: any) {
      toast({
        title: "Login failed",
        description: err.message,
        variant: "destructive",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="flex justify-center mb-4">
            <img src={logoHorizontal} alt="TomeVox" className="h-12 w-auto" />
          </div>
          <CardTitle data-testid="text-login-title">Sign In</CardTitle>
          <CardDescription>Enter your credentials to continue</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Username"
                autoComplete="username"
                data-testid="input-username"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Password"
                autoComplete="current-password"
                data-testid="input-password"
              />
            </div>
            <Button
              type="submit"
              className="w-full"
              disabled={isSubmitting || !username || !password}
              data-testid="button-login"
            >
              {isSubmitting ? "Signing in..." : "Sign In"}
            </Button>
          </form>
          {registrationMode !== "disabled" && (
            <div className="mt-4 text-center">
              <button
                onClick={onShowRegister}
                className="text-sm text-primary hover:underline"
                data-testid="link-create-account"
              >
                Create Account
              </button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
