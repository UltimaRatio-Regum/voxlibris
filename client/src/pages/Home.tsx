import { useState } from "react";
import { Sparkles, List, Settings, BookOpen, Users, LogOut, Key, Shield, HelpCircle } from "lucide-react";
import { ThemeToggle } from "@/components/ThemeToggle";
import { ProjectWizardTab } from "@/components/ProjectWizardTab";
import { JobsPanel } from "@/components/JobsPanel";
import { SettingsTab } from "@/components/SettingsTab";
import { ProjectsListPanel } from "@/components/ProjectsListPanel";
import { ProjectEditor } from "@/components/ProjectEditor";
import { AdminUsersPage } from "@/pages/AdminUsersPage";
import { ChangePasswordDialog } from "@/components/ChangePasswordDialog";
import { useAuth } from "@/lib/auth";
import logoHorizontal from "@assets/vl_full_logo_horizontal.png";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

type TabValue = "wizard" | "jobs" | "settings" | "projects" | "users";

export default function Home() {
  const { user, logout } = useAuth();
  const isAdmin = user?.userType === "administrator";
  const [activeTab, setActiveTab] = useState<TabValue>("wizard");
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
  const [showChangePassword, setShowChangePassword] = useState(false);

  const tabs = [
    { value: "wizard" as const, label: "Project Wizard", icon: Sparkles },
    { value: "projects" as const, label: "Projects", icon: BookOpen },
    { value: "jobs" as const, label: "Jobs", icon: List },
    { value: "settings" as const, label: "Settings", icon: Settings },
    ...(isAdmin ? [{ value: "users" as const, label: "Users", icon: Users }] : []),
  ];

  const handleSelectProject = (projectId: string) => {
    setEditingProjectId(projectId);
  };

  const handleBackToList = () => {
    setEditingProjectId(null);
  };

  const handleWizardProjectCreated = (projectId: string) => {
    setActiveTab("projects");
    setEditingProjectId(projectId);
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container flex h-16 items-center justify-between gap-4 px-4 mx-auto">
          <div className="flex items-center">
            <img 
              src={logoHorizontal} 
              alt="VoxLibris" 
              className="h-10 w-auto"
            />
          </div>
          <div className="flex items-center gap-3">
            <a href="/docs">
              <Button variant="ghost" size="sm" className="gap-1.5" data-testid="link-docs">
                <HelpCircle className="h-4 w-4" />
                <span className="hidden sm:inline">Docs</span>
              </Button>
            </a>
            <ThemeToggle />
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm" className="gap-2" data-testid="button-user-menu">
                  {isAdmin && <Shield className="h-3 w-3" />}
                  <span className="hidden sm:inline" data-testid="text-user-display-name">
                    {user?.displayName || user?.username}
                  </span>
                  {isAdmin && (
                    <Badge variant="secondary" className="text-xs py-0 px-1.5 hidden sm:inline-flex" data-testid="badge-admin">
                      Admin
                    </Badge>
                  )}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem className="text-xs text-muted-foreground" disabled>
                  Signed in as {user?.username}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => setShowChangePassword(true)} data-testid="button-change-password">
                  <Key className="h-4 w-4 mr-2" />
                  Change Password
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={logout} data-testid="button-logout">
                  <LogOut className="h-4 w-4 mr-2" />
                  Sign Out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-6">
        <div className="w-full">
          <div className={cn("grid w-full max-w-xl mx-auto mb-6 p-1 bg-muted rounded-lg", isAdmin ? "grid-cols-5" : "grid-cols-4")}>
            {tabs.map((tab) => (
              <button
                key={tab.value}
                onClick={() => {
                  setActiveTab(tab.value);
                  if (tab.value !== "projects") {
                    setEditingProjectId(null);
                  }
                }}
                className={cn(
                  "flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium rounded-md transition-colors",
                  activeTab === tab.value
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                )}
                data-testid={`tab-${tab.value}`}
              >
                <tab.icon className="h-4 w-4" />
                <span className="hidden sm:inline">{tab.label}</span>
              </button>
            ))}
          </div>

          <div className={cn(activeTab === "wizard" ? "block" : "hidden")}>
            <ProjectWizardTab onProjectCreated={handleWizardProjectCreated} />
          </div>

          <div className={cn(activeTab === "projects" ? "block" : "hidden")}>
            {editingProjectId ? (
              <ProjectEditor
                projectId={editingProjectId}
                onBack={handleBackToList}
              />
            ) : (
              <ProjectsListPanel onSelectProject={handleSelectProject} />
            )}
          </div>

          <div className={cn(activeTab === "jobs" ? "block" : "hidden")}>
            <div className="max-w-4xl mx-auto">
              <JobsPanel />
            </div>
          </div>

          <div className={cn(activeTab === "settings" ? "block" : "hidden")}>
            <div className="max-w-4xl mx-auto">
              <SettingsTab />
            </div>
          </div>

          {isAdmin && (
            <div className={cn(activeTab === "users" ? "block" : "hidden")}>
              <div className="max-w-4xl mx-auto">
                <AdminUsersPage />
              </div>
            </div>
          )}
        </div>
      </main>

      <ChangePasswordDialog open={showChangePassword} onOpenChange={setShowChangePassword} />
    </div>
  );
}
