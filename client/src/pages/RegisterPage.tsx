import { useState, useEffect } from "react";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { useToast } from "@/hooks/use-toast";
import logoHorizontal from "@assets/vl_full_logo_horizontal.png";

interface RegisterPageProps {
  onShowLogin: () => void;
}

export function RegisterPage({ onShowLogin }: RegisterPageProps) {
  const { register } = useAuth();
  const { toast } = useToast();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [email, setEmail] = useState("");
  const [invitationCode, setInvitationCode] = useState("");
  const [ageConfirmed, setAgeConfirmed] = useState(false);
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
    if (password !== confirmPassword) {
      toast({ title: "Passwords don't match", variant: "destructive" });
      return;
    }
    if (!ageConfirmed) {
      toast({
        title: "Age confirmation required",
        description: "You must confirm you are over 13 years of age.",
        variant: "destructive",
      });
      return;
    }
    setIsSubmitting(true);
    try {
      await register({
        username,
        password,
        email,
        ageConfirmed: true,
        invitationCode: registrationMode === "invite-only" ? invitationCode : undefined,
      });
    } catch (err: any) {
      toast({
        title: "Registration failed",
        description: err.message,
        variant: "destructive",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  if (registrationMode === "disabled") {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <Card className="w-full max-w-md">
          <CardHeader className="text-center">
            <CardTitle>Registration Disabled</CardTitle>
            <CardDescription>
              Self-registration is currently disabled. Contact an administrator.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button variant="outline" className="w-full" onClick={onShowLogin} data-testid="button-back-to-login">
              Back to Login
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="flex justify-center mb-4">
            <img src={logoHorizontal} alt="VoxLibris" className="h-12 w-auto" />
          </div>
          <CardTitle data-testid="text-register-title">Create Account</CardTitle>
          <CardDescription>
            {registrationMode === "invite-only"
              ? "Registration requires an invitation code"
              : "Create your account to get started"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="reg-username">Username</Label>
              <Input
                id="reg-username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Choose a username"
                data-testid="input-reg-username"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="reg-email">Email</Label>
              <Input
                id="reg-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="your@email.com"
                data-testid="input-reg-email"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="reg-password">Password</Label>
              <Input
                id="reg-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 8 characters"
                data-testid="input-reg-password"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="reg-confirm-password">Confirm Password</Label>
              <Input
                id="reg-confirm-password"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Re-enter your password"
                data-testid="input-reg-confirm-password"
              />
            </div>
            {registrationMode === "invite-only" && (
              <div className="space-y-2">
                <Label htmlFor="invitation-code">Invitation Code</Label>
                <Input
                  id="invitation-code"
                  value={invitationCode}
                  onChange={(e) => setInvitationCode(e.target.value)}
                  placeholder="Enter invitation code"
                  data-testid="input-invitation-code"
                />
              </div>
            )}
            <div className="flex items-center space-x-2">
              <Checkbox
                id="age-confirm"
                checked={ageConfirmed}
                onCheckedChange={(v) => setAgeConfirmed(v === true)}
                data-testid="checkbox-age-confirm"
              />
              <Label htmlFor="age-confirm" className="text-sm">
                I confirm I am over 13 years of age
              </Label>
            </div>
            <Button
              type="submit"
              className="w-full"
              disabled={
                isSubmitting ||
                !username ||
                password.length < 8 ||
                password !== confirmPassword ||
                !email ||
                !ageConfirmed ||
                (registrationMode === "invite-only" && !invitationCode)
              }
              data-testid="button-register"
            >
              {isSubmitting ? "Creating account..." : "Create Account"}
            </Button>
          </form>
          <div className="mt-4 text-center">
            <button
              onClick={onShowLogin}
              className="text-sm text-primary hover:underline"
              data-testid="link-back-to-login"
            >
              Already have an account? Sign In
            </button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
