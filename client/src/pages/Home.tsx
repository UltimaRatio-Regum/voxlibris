import { BookAudio, Upload, Settings, List } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ThemeToggle } from "@/components/ThemeToggle";
import { BeginnerTab } from "@/components/BeginnerTab";
import { AdvancedTab } from "@/components/AdvancedTab";
import { JobsPanel } from "@/components/JobsPanel";

export default function Home() {
  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container flex h-16 items-center justify-between gap-4 px-4 mx-auto">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center h-10 w-10 rounded-md bg-primary text-primary-foreground">
              <BookAudio className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-lg font-semibold">Narrator AI</h1>
              <p className="text-xs text-muted-foreground hidden sm:block">Text to Audiobook Generator</p>
            </div>
          </div>
          <ThemeToggle />
        </div>
      </header>

      <main className="container mx-auto px-4 py-6">
        <Tabs defaultValue="beginner" className="w-full">
          <TabsList className="grid w-full grid-cols-3 max-w-md mx-auto mb-6">
            <TabsTrigger value="beginner" className="gap-2" data-testid="tab-beginner">
              <Upload className="h-4 w-4" />
              <span className="hidden sm:inline">Beginner</span>
            </TabsTrigger>
            <TabsTrigger value="advanced" className="gap-2" data-testid="tab-advanced">
              <Settings className="h-4 w-4" />
              <span className="hidden sm:inline">Advanced</span>
            </TabsTrigger>
            <TabsTrigger value="jobs" className="gap-2" data-testid="tab-jobs">
              <List className="h-4 w-4" />
              <span className="hidden sm:inline">Job Monitor</span>
            </TabsTrigger>
          </TabsList>

          <TabsContent value="beginner">
            <BeginnerTab />
          </TabsContent>

          <TabsContent value="advanced">
            <AdvancedTab />
          </TabsContent>

          <TabsContent value="jobs">
            <div className="max-w-4xl mx-auto">
              <JobsPanel />
            </div>
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}
