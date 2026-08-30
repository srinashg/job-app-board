"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/lib/auth";

const LINKS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/jobs", label: "My five" },
  { href: "/applications", label: "Applications" },
  { href: "/resumes", label: "Resumes" },
  { href: "/preferences", label: "Filters" },
  { href: "/settings/privacy", label: "Privacy" },
];

export function Nav() {
  const pathname = usePathname();
  const { user, signOut } = useAuth();

  if (!user) return null;

  const links = user.role === "admin" ? [...LINKS, { href: "/admin/jobs", label: "Admin" }] : LINKS;

  return (
    <nav className="top-nav">
      <div className="top-nav-inner">
        <Link href="/dashboard" className="brand">
          Job Board
        </Link>
        <div className="nav-links">
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="nav-link"
              aria-current={
                pathname === link.href || pathname.startsWith(`${link.href}/`) ? "page" : undefined
              }
            >
              {link.label}
            </Link>
          ))}
        </div>
        <div className="row">
          <span className="subtle">{user.email}</span>
          <button type="button" className="ghost small" onClick={signOut}>
            Sign out
          </button>
        </div>
      </div>
    </nav>
  );
}
