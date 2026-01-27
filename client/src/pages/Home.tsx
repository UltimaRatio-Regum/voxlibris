import { useState } from "react";
import { Upload, Sliders, List, Settings } from "lucide-react";
import { ThemeToggle } from "@/components/ThemeToggle";
import { BeginnerTab } from "@/components/BeginnerTab";
import { AdvancedTab } from "@/components/AdvancedTab";
import { JobsPanel } from "@/components/JobsPanel";
import { SettingsTab } from "@/components/SettingsTab";
import logoHorizontal from "@assets/vl_full_logo_horizontal.png";
import { cn } from "@/lib/utils";

type TabValue = "beginner" | "advanced" | "jobs" | "settings";

export default function Home() {
  const [activeTab, setActiveTab] = useState<TabValue>("beginner");

  const tabs = [
    { value: "beginner" as const, label: "Beginner", icon: Upload },
    { value: "advanced" as const, label: "Advanced", icon: Sliders },
    { value: "jobs" as const, label: "Jobs", icon: List },
    { value: "settings" as const, label: "Settings", icon: Settings },
  ];

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
          <ThemeToggle />
        </div>
      </header>

      <main className="container mx-auto px-4 py-6">
        <div className="w-full">
          <div className="grid w-full grid-cols-4 max-w-lg mx-auto mb-6 p-1 bg-muted rounded-lg">
            {tabs.map((tab) => (
              <button
                key={tab.value}
                onClick={() => setActiveTab(tab.value)}
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

          <div className={cn(activeTab === "beginner" ? "block" : "hidden")}>
            <BeginnerTab />
          </div>

          <div className={cn(activeTab === "advanced" ? "block" : "hidden")}>
            <AdvancedTab />
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
        </div>
      </main>
    </div>
  );
}
