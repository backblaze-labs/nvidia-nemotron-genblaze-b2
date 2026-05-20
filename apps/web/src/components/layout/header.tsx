"use client";

import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { SidebarTrigger } from "@/components/ui/sidebar";

const pageTitles: Record<string, string> = {
  "/": "Briefing",
};

export function Header() {
  const pathname = usePathname();
  const { theme, setTheme } = useTheme();
  const pageTitle = pageTitles[pathname] || "Page";

  return (
    <header className="flex h-14 items-center gap-3 bg-nav text-nav-foreground px-4 border-b border-white/10">
      <SidebarTrigger className="h-8 w-8 text-nav-foreground/80 hover:text-nav-foreground hover:bg-white/10 rounded-md" />
      <Breadcrumb>
        <BreadcrumbList className="text-sm">
          <BreadcrumbItem>
            <BreadcrumbLink
              href="/"
              className="text-nav-foreground/80 hover:text-nav-foreground font-medium"
            >
              nvidia-nemotron-genblaze-b2
            </BreadcrumbLink>
          </BreadcrumbItem>
          {pathname !== "/" && (
            <>
              <BreadcrumbSeparator className="text-nav-foreground/40">/</BreadcrumbSeparator>
              <BreadcrumbItem>
                <BreadcrumbPage className="text-nav-foreground font-semibold">
                  {pageTitle}
                </BreadcrumbPage>
              </BreadcrumbItem>
            </>
          )}
        </BreadcrumbList>
      </Breadcrumb>

      <div className="ml-auto flex items-center gap-1">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-nav-foreground/80 hover:text-nav-foreground hover:bg-white/10 rounded-md"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label="Toggle theme"
        >
          <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
          <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
        </Button>
      </div>
    </header>
  );
}
