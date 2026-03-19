import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/lib/auth";
import { apiRequest } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Plus, Trash2, Key, UserCog, Shield, Copy, Check } from "lucide-react";
import type { User } from "@shared/schema";

export function AdminUsersPage() {
  const { user: currentUser } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showResetPasswordDialog, setShowResetPasswordDialog] = useState<string | null>(null);
  const [showDeleteDialog, setShowDeleteDialog] = useState<string | null>(null);
  const [newUser, setNewUser] = useState({ username: "", password: "", email: "", displayName: "", userType: "user" });
  const [newUserConfirmPassword, setNewUserConfirmPassword] = useState("");
  const [resetPassword, setResetPassword] = useState("");
  const [resetPasswordConfirm, setResetPasswordConfirm] = useState("");
  const [copiedCode, setCopiedCode] = useState<string | null>(null);

  const { data: users = [], isLoading } = useQuery<User[]>({
    queryKey: ["/api/admin/users"],
  });

  const { data: regModeData } = useQuery<{ mode: string }>({
    queryKey: ["/api/admin/settings/registration-mode"],
  });

  const { data: invitationCodes = [] } = useQuery<any[]>({
    queryKey: ["/api/admin/invitation-codes"],
    enabled: regModeData?.mode === "invite-only",
  });

  const createUserMutation = useMutation({
    mutationFn: async (data: typeof newUser) => {
      const res = await apiRequest("POST", "/api/admin/users", data);
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/admin/users"] });
      setShowCreateDialog(false);
      setNewUser({ username: "", password: "", email: "", displayName: "", userType: "user" });
      setNewUserConfirmPassword("");
      toast({ title: "User created" });
    },
    onError: (err: Error) => {
      toast({ title: "Failed to create user", description: err.message, variant: "destructive" });
    },
  });

  const toggleUserMutation = useMutation({
    mutationFn: async ({ id, isEnabled }: { id: string; isEnabled: boolean }) => {
      const res = await apiRequest("PATCH", `/api/admin/users/${id}`, { isEnabled });
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/admin/users"] });
      toast({ title: "User updated" });
    },
  });

  const deleteUserMutation = useMutation({
    mutationFn: async (id: string) => {
      const res = await apiRequest("DELETE", `/api/admin/users/${id}`);
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/admin/users"] });
      setShowDeleteDialog(null);
      toast({ title: "User deleted" });
    },
    onError: (err: Error) => {
      toast({ title: "Failed to delete user", description: err.message, variant: "destructive" });
    },
  });

  const resetPasswordMutation = useMutation({
    mutationFn: async ({ id, newPassword }: { id: string; newPassword: string }) => {
      const res = await apiRequest("POST", `/api/admin/users/${id}/reset-password`, { newPassword });
      return res.json();
    },
    onSuccess: () => {
      setShowResetPasswordDialog(null);
      setResetPassword("");
      setResetPasswordConfirm("");
      toast({ title: "Password reset" });
    },
    onError: (err: Error) => {
      toast({ title: "Failed to reset password", description: err.message, variant: "destructive" });
    },
  });

  const updateRegModeMutation = useMutation({
    mutationFn: async (mode: string) => {
      const res = await apiRequest("PUT", "/api/admin/settings/registration-mode", { mode });
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/admin/settings/registration-mode"] });
      queryClient.invalidateQueries({ queryKey: ["/api/admin/invitation-codes"] });
      toast({ title: "Registration mode updated" });
    },
  });

  const generateCodeMutation = useMutation({
    mutationFn: async () => {
      const res = await apiRequest("POST", "/api/admin/invitation-codes", {});
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/admin/invitation-codes"] });
      toast({ title: "Invitation code generated" });
    },
  });

  const deleteCodeMutation = useMutation({
    mutationFn: async (id: string) => {
      const res = await apiRequest("DELETE", `/api/admin/invitation-codes/${id}`);
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/admin/invitation-codes"] });
      toast({ title: "Invitation code deleted" });
    },
  });

  const copyCode = (code: string) => {
    navigator.clipboard.writeText(code);
    setCopiedCode(code);
    setTimeout(() => setCopiedCode(null), 2000);
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div>
              <CardTitle className="flex items-center gap-2">
                <UserCog className="h-5 w-5" />
                User Management
              </CardTitle>
              <CardDescription>Manage user accounts and permissions</CardDescription>
            </div>
            <Button size="sm" onClick={() => setShowCreateDialog(true)} data-testid="button-create-user">
              <Plus className="h-4 w-4 mr-2" />
              Create User
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="text-center py-8 text-muted-foreground animate-pulse">Loading users...</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Username</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Display Name</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((u) => (
                  <TableRow key={u.id} data-testid={`row-user-${u.id}`}>
                    <TableCell className="font-medium" data-testid={`text-username-${u.id}`}>{u.username}</TableCell>
                    <TableCell>{u.email || "—"}</TableCell>
                    <TableCell>{u.displayName || "—"}</TableCell>
                    <TableCell>
                      <Badge variant={u.userType === "administrator" ? "default" : "secondary"} data-testid={`badge-role-${u.id}`}>
                        {u.userType === "administrator" ? (
                          <span className="flex items-center gap-1"><Shield className="h-3 w-3" /> Admin</span>
                        ) : "User"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={u.isEnabled ? "outline" : "destructive"} data-testid={`badge-status-${u.id}`}>
                        {u.isEnabled ? "Enabled" : "Disabled"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => toggleUserMutation.mutate({ id: u.id, isEnabled: !u.isEnabled })}
                          disabled={u.id === currentUser?.id}
                          data-testid={`button-toggle-${u.id}`}
                        >
                          {u.isEnabled ? "Disable" : "Enable"}
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => { setShowResetPasswordDialog(u.id); setResetPassword(""); setResetPasswordConfirm(""); }}
                          data-testid={`button-reset-password-${u.id}`}
                        >
                          <Key className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="text-destructive"
                          onClick={() => setShowDeleteDialog(u.id)}
                          disabled={u.id === currentUser?.id}
                          data-testid={`button-delete-user-${u.id}`}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Registration Settings</CardTitle>
          <CardDescription>Control how new users can register</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>Registration Mode</Label>
            <Select
              value={regModeData?.mode || "disabled"}
              onValueChange={(v) => updateRegModeMutation.mutate(v)}
            >
              <SelectTrigger data-testid="select-registration-mode">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="disabled">Disabled</SelectItem>
                <SelectItem value="invite-only">Invite Only</SelectItem>
                <SelectItem value="open">Open Registration</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {regModeData?.mode === "invite-only" && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label>Invitation Codes</Label>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => generateCodeMutation.mutate()}
                  disabled={generateCodeMutation.isPending}
                  data-testid="button-generate-code"
                >
                  <Plus className="h-4 w-4 mr-2" />
                  Generate Code
                </Button>
              </div>
              {invitationCodes.length > 0 ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Code</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Used By</TableHead>
                      <TableHead>Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {invitationCodes.map((ic: any) => (
                      <TableRow key={ic.id} data-testid={`row-code-${ic.id}`}>
                        <TableCell>
                          <code className="text-sm font-mono bg-muted px-2 py-1 rounded" data-testid={`text-code-${ic.id}`}>
                            {ic.code}
                          </code>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="ml-1 h-6 w-6"
                            onClick={() => copyCode(ic.code)}
                            data-testid={`button-copy-code-${ic.id}`}
                          >
                            {copiedCode === ic.code ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                          </Button>
                        </TableCell>
                        <TableCell>
                          <Badge variant={ic.usedBy ? "secondary" : "outline"}>
                            {ic.usedBy ? "Used" : "Available"}
                          </Badge>
                        </TableCell>
                        <TableCell>{ic.usedBy || "—"}</TableCell>
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="text-destructive"
                            onClick={() => deleteCodeMutation.mutate(ic.id)}
                            data-testid={`button-delete-code-${ic.id}`}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-4">No invitation codes generated yet</p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create User</DialogTitle>
            <DialogDescription>Create a new user account</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Username</Label>
              <Input
                value={newUser.username}
                onChange={(e) => setNewUser({ ...newUser, username: e.target.value })}
                data-testid="input-new-username"
              />
            </div>
            <div className="space-y-2">
              <Label>Email</Label>
              <Input
                type="email"
                value={newUser.email}
                onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
                data-testid="input-new-email"
              />
            </div>
            <div className="space-y-2">
              <Label>Display Name</Label>
              <Input
                value={newUser.displayName}
                onChange={(e) => setNewUser({ ...newUser, displayName: e.target.value })}
                data-testid="input-new-display-name"
              />
            </div>
            <div className="space-y-2">
              <Label>Password</Label>
              <Input
                type="password"
                value={newUser.password}
                onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
                placeholder="At least 8 characters"
                data-testid="input-new-password"
              />
            </div>
            <div className="space-y-2">
              <Label>Confirm Password</Label>
              <Input
                type="password"
                value={newUserConfirmPassword}
                onChange={(e) => setNewUserConfirmPassword(e.target.value)}
                placeholder="Re-enter password"
                data-testid="input-new-password-confirm"
              />
            </div>
            <div className="space-y-2">
              <Label>Role</Label>
              <Select value={newUser.userType} onValueChange={(v) => setNewUser({ ...newUser, userType: v })}>
                <SelectTrigger data-testid="select-new-user-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="user">User</SelectItem>
                  <SelectItem value="administrator">Administrator</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={() => createUserMutation.mutate(newUser)}
              disabled={!newUser.username || newUser.password.length < 8 || newUser.password !== newUserConfirmPassword || createUserMutation.isPending}
              data-testid="button-submit-create-user"
            >
              {createUserMutation.isPending ? "Creating..." : "Create User"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!showResetPasswordDialog} onOpenChange={(v) => !v && setShowResetPasswordDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reset Password</DialogTitle>
            <DialogDescription>
              Enter a new password for this user
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>New Password</Label>
              <Input
                type="password"
                value={resetPassword}
                onChange={(e) => setResetPassword(e.target.value)}
                placeholder="At least 8 characters"
                data-testid="input-reset-password"
              />
            </div>
            <div className="space-y-2">
              <Label>Confirm New Password</Label>
              <Input
                type="password"
                value={resetPasswordConfirm}
                onChange={(e) => setResetPasswordConfirm(e.target.value)}
                placeholder="Re-enter new password"
                data-testid="input-reset-password-confirm"
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={() => {
                if (showResetPasswordDialog) {
                  resetPasswordMutation.mutate({ id: showResetPasswordDialog, newPassword: resetPassword });
                }
              }}
              disabled={resetPassword.length < 8 || resetPassword !== resetPasswordConfirm || resetPasswordMutation.isPending}
              data-testid="button-submit-reset-password"
            >
              {resetPasswordMutation.isPending ? "Resetting..." : "Reset Password"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!showDeleteDialog} onOpenChange={(v) => !v && setShowDeleteDialog(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete User</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure? This action cannot be undone. The user and all their data will be permanently deleted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="button-cancel-delete">Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => showDeleteDialog && deleteUserMutation.mutate(showDeleteDialog)}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              data-testid="button-confirm-delete"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
