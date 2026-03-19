import { useState, useEffect, useMemo } from "react";
import { useRoute, useLocation, Link } from "wouter";
import { useQuery } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import rehypeHighlight from "rehype-highlight";
import "highlight.js/styles/github-dark.css";
import { Search, BookOpen, ChevronRight, ChevronDown, ArrowLeft, Menu, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ThemeToggle } from "@/components/ThemeToggle";
import logoHorizontal from "@assets/vl_full_logo_horizontal.png";

interface DocEntry {
  slug: string;
  title: string;
  description: string;
  category: string;
  order: number;
  keywords: string[];
}

interface DocContent extends DocEntry {
  content: string;
}

function useDocsManifest() {
  return useQuery<DocEntry[]>({
    queryKey: ["/api/docs/manifest"],
  });
}

function useDocContent(slug: string | null) {
  return useQuery<DocContent>({
    queryKey: ["/api/docs", slug],
    enabled: !!slug,
  });
}

function extractHeadings(markdown: string) {
  const headings: { level: number; text: string; id: string }[] = [];
  const lines = markdown.split("\n");
  for (const line of lines) {
    const match = line.match(/^(#{2,4})\s+(.+)$/);
    if (match) {
      const level = match[1].length;
      const text = match[2].trim();
      const id = text.toLowerCase().replace(/[^\w\s-]/g, "").replace(/\s+/g, "-");
      headings.push({ level, text, id });
    }
  }
  return headings;
}

function DocsSidebar({
  manifest,
  currentSlug,
  searchQuery,
  onSearchChange,
  onSelectDoc,
  mobileOpen,
  onCloseMobile,
}: {
  manifest: DocEntry[];
  currentSlug: string | null;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  onSelectDoc: (slug: string) => void;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}) {
  const [collapsedCategories, setCollapsedCategories] = useState<Set<string>>(new Set());

  const filtered = useMemo(() => {
    if (!searchQuery.trim()) return manifest;
    const q = searchQuery.toLowerCase();
    return manifest.filter(
      (doc) =>
        doc.title.toLowerCase().includes(q) ||
        doc.description.toLowerCase().includes(q) ||
        doc.keywords.some((k) => k.toLowerCase().includes(q))
    );
  }, [manifest, searchQuery]);

  const grouped = useMemo(() => {
    const groups: Record<string, DocEntry[]> = {};
    for (const doc of filtered) {
      if (!groups[doc.category]) groups[doc.category] = [];
      groups[doc.category].push(doc);
    }
    return groups;
  }, [filtered]);

  const categoryOrder = ["Basics", "Projects", "Audio", "Configuration", "Reference"];

  const sortedCategories = Object.keys(grouped).sort((a, b) => {
    const ai = categoryOrder.indexOf(a);
    const bi = categoryOrder.indexOf(b);
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
  });

  const toggleCategory = (cat: string) => {
    setCollapsedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  };

  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-50 w-72 border-r bg-background flex flex-col transition-transform duration-200 lg:relative lg:translate-x-0",
        mobileOpen ? "translate-x-0" : "-translate-x-full"
      )}
    >
      <div className="p-4 border-b">
        <div className="flex items-center justify-between mb-3">
          <Link href="/docs" className="flex items-center gap-2">
            <img src={logoHorizontal} alt="VoxLibris" className="h-7 w-auto" />
            <span className="text-sm font-medium text-muted-foreground">Docs</span>
          </Link>
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={onCloseMobile}
            aria-label="Close sidebar"
            data-testid="button-close-docs-sidebar"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search docs..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            className="pl-8 h-9"
            data-testid="input-docs-search"
          />
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        <nav className="p-3 space-y-1" data-testid="docs-sidebar-nav">
          {sortedCategories.map((category) => {
            const isCollapsed = collapsedCategories.has(category);
            return (
              <div key={category}>
                <button
                  onClick={() => toggleCategory(category)}
                  className="flex items-center gap-1.5 w-full px-2 py-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors"
                  aria-expanded={!isCollapsed}
                  data-testid={`button-category-${category.toLowerCase()}`}
                >
                  {isCollapsed ? (
                    <ChevronRight className="h-3 w-3" />
                  ) : (
                    <ChevronDown className="h-3 w-3" />
                  )}
                  {category}
                </button>
                {!isCollapsed && (
                  <div className="ml-2 space-y-0.5">
                    {grouped[category].map((doc) => (
                      <button
                        key={doc.slug}
                        onClick={() => {
                          onSelectDoc(doc.slug);
                          onCloseMobile();
                        }}
                        className={cn(
                          "flex items-center gap-2 w-full px-3 py-1.5 text-sm rounded-md transition-colors text-left",
                          currentSlug === doc.slug
                            ? "bg-primary/10 text-primary font-medium"
                            : "text-muted-foreground hover:text-foreground hover:bg-muted"
                        )}
                        data-testid={`link-doc-${doc.slug}`}
                      >
                        <BookOpen className="h-3.5 w-3.5 shrink-0" />
                        <span className="truncate">{doc.title}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </nav>
      </div>
      <div className="p-3 border-t">
        <a href="/" className="block">
          <Button variant="ghost" size="sm" className="w-full justify-start gap-2" data-testid="link-back-to-app">
            <ArrowLeft className="h-4 w-4" />
            Back to App
          </Button>
        </a>
      </div>
    </aside>
  );
}

function OnThisPage({ headings }: { headings: { level: number; text: string; id: string }[] }) {
  if (headings.length === 0) return null;
  return (
    <aside className="hidden xl:block w-56 shrink-0">
      <div className="sticky top-20">
        <h4 className="text-sm font-semibold mb-3">On This Page</h4>
        <nav className="space-y-1">
          {headings.map((h) => (
            <a
              key={h.id}
              href={`#${h.id}`}
              className={cn(
                "block text-sm text-muted-foreground hover:text-foreground transition-colors",
                h.level === 2 && "pl-0",
                h.level === 3 && "pl-3",
                h.level === 4 && "pl-6"
              )}
            >
              {h.text}
            </a>
          ))}
        </nav>
      </div>
    </aside>
  );
}

function MarkdownRenderer({
  content,
  onNavigate,
}: {
  content: string;
  onNavigate: (slug: string) => void;
}) {
  return (
    <div className="prose prose-sm dark:prose-invert max-w-none prose-headings:scroll-mt-20 prose-h1:text-3xl prose-h1:font-bold prose-h2:text-xl prose-h2:font-semibold prose-h2:border-b prose-h2:pb-2 prose-h2:mt-8 prose-h3:text-lg prose-table:text-sm prose-th:bg-muted prose-th:px-3 prose-th:py-2 prose-td:px-3 prose-td:py-2 prose-code:bg-muted prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-sm prose-code:before:content-none prose-code:after:content-none prose-blockquote:border-primary prose-a:text-primary prose-a:no-underline hover:prose-a:underline">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw, rehypeHighlight]}
        components={{
          a: ({ href, children, ...props }) => {
            if (href && href.startsWith("./")) {
              const slug = href.replace("./", "");
              return (
                <a
                  href={`/docs/${slug}`}
                  onClick={(e) => {
                    e.preventDefault();
                    onNavigate(slug);
                  }}
                  className="text-primary cursor-pointer hover:underline"
                  {...props}
                >
                  {children}
                </a>
              );
            }
            return (
              <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
                {children}
              </a>
            );
          },
          h2: ({ children, ...props }) => {
            const text = typeof children === "string" ? children : String(children);
            const id = text.toLowerCase().replace(/[^\w\s-]/g, "").replace(/\s+/g, "-");
            return (
              <h2 id={id} {...props}>
                {children}
              </h2>
            );
          },
          h3: ({ children, ...props }) => {
            const text = typeof children === "string" ? children : String(children);
            const id = text.toLowerCase().replace(/[^\w\s-]/g, "").replace(/\s+/g, "-");
            return (
              <h3 id={id} {...props}>
                {children}
              </h3>
            );
          },
          h4: ({ children, ...props }) => {
            const text = typeof children === "string" ? children : String(children);
            const id = text.toLowerCase().replace(/[^\w\s-]/g, "").replace(/\s+/g, "-");
            return (
              <h4 id={id} {...props}>
                {children}
              </h4>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

export default function DocsPage() {
  const [, setLocation] = useLocation();
  const [matchSlug, params] = useRoute("/docs/:slug");
  const slug = matchSlug ? params?.slug || null : null;
  const [searchQuery, setSearchQuery] = useState("");
  const [mobileOpen, setMobileOpen] = useState(false);

  const { data: manifest = [], isLoading: manifestLoading } = useDocsManifest();
  const activeSlug = slug || (manifest.length > 0 ? manifest[0].slug : null);
  const { data: doc, isLoading: docLoading } = useDocContent(activeSlug);

  const headings = useMemo(() => {
    if (!doc?.content) return [];
    return extractHeadings(doc.content);
  }, [doc?.content]);

  const handleNavigate = (docSlug: string) => {
    setLocation(`/docs/${docSlug}`);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  useEffect(() => {
    if (doc?.title) {
      document.title = `${doc.title} - VoxLibris Docs`;
    } else {
      document.title = "VoxLibris Documentation";
    }
  }, [doc?.title]);

  if (manifestLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading documentation...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex">
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <DocsSidebar
        manifest={manifest}
        currentSlug={activeSlug}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        onSelectDoc={handleNavigate}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />

      <div className="flex-1 flex flex-col min-w-0">
        <header className="sticky top-0 z-30 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
          <div className="flex items-center h-14 px-4 gap-3">
            <Button
              variant="ghost"
              size="icon"
              className="lg:hidden"
              onClick={() => setMobileOpen(true)}
              aria-label="Open sidebar"
              data-testid="button-open-docs-sidebar"
            >
              <Menu className="h-5 w-5" />
            </Button>
            <div className="flex-1 min-w-0">
              {doc && (
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-muted-foreground">{doc.category}</span>
                  <ChevronRight className="h-3 w-3 text-muted-foreground" />
                  <span className="font-medium truncate">{doc.title}</span>
                </div>
              )}
            </div>
            <ThemeToggle />
          </div>
        </header>

        <div className="flex-1 flex justify-center">
          <div className="flex w-full max-w-5xl px-4 py-8 gap-8">
            <main className="flex-1 min-w-0" data-testid="docs-content">
              {docLoading ? (
                <div className="space-y-4 animate-pulse">
                  <div className="h-8 bg-muted rounded w-3/4" />
                  <div className="h-4 bg-muted rounded w-full" />
                  <div className="h-4 bg-muted rounded w-5/6" />
                  <div className="h-4 bg-muted rounded w-2/3" />
                </div>
              ) : doc ? (
                <>
                  <MarkdownRenderer content={doc.content} onNavigate={handleNavigate} />
                  <div className="mt-12 pt-6 border-t flex justify-between" data-testid="docs-pagination">
                    {(() => {
                      const idx = manifest.findIndex((m) => m.slug === activeSlug);
                      const prev = idx > 0 ? manifest[idx - 1] : null;
                      const next = idx < manifest.length - 1 ? manifest[idx + 1] : null;
                      return (
                        <>
                          <div>
                            {prev && (
                              <Button
                                variant="ghost"
                                className="gap-2"
                                onClick={() => handleNavigate(prev.slug)}
                                data-testid="button-prev-doc"
                              >
                                <ArrowLeft className="h-4 w-4" />
                                {prev.title}
                              </Button>
                            )}
                          </div>
                          <div>
                            {next && (
                              <Button
                                variant="ghost"
                                className="gap-2"
                                onClick={() => handleNavigate(next.slug)}
                                data-testid="button-next-doc"
                              >
                                {next.title}
                                <ChevronRight className="h-4 w-4" />
                              </Button>
                            )}
                          </div>
                        </>
                      );
                    })()}
                  </div>
                </>
              ) : (
                <div className="text-center text-muted-foreground py-12">
                  <BookOpen className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p>Select a document from the sidebar to get started.</p>
                </div>
              )}
            </main>
            <OnThisPage headings={headings} />
          </div>
        </div>
      </div>
    </div>
  );
}
