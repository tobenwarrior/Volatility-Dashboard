"use client";

import { useState, useRef, useEffect, useCallback } from "react";

export type Section = {
  id: string;
  label: string;
  visible: boolean;
};

interface LayoutMenuProps {
  sections: Section[];
  onChange: (sections: Section[]) => void;
}

export default function LayoutMenu({ sections, onChange }: LayoutMenuProps) {
  const [open, setOpen] = useState(false);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [overIndex, setOverIndex] = useState<number | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const toggle = (id: string) => {
    onChange(
      sections.map((s) => (s.id === id ? { ...s, visible: !s.visible } : s))
    );
  };

  const handleDragStart = useCallback((index: number) => {
    setDragIndex(index);
  }, []);

  const handleDragOver = useCallback(
    (e: React.DragEvent, index: number) => {
      e.preventDefault();
      if (dragIndex === null || dragIndex === index) return;
      setOverIndex(index);
    },
    [dragIndex]
  );

  const handleDrop = useCallback(
    (index: number) => {
      if (dragIndex === null || dragIndex === index) return;
      const next = [...sections];
      const [moved] = next.splice(dragIndex, 1);
      next.splice(index, 0, moved);
      onChange(next);
      setDragIndex(null);
      setOverIndex(null);
    },
    [dragIndex, sections, onChange]
  );

  const handleDragEnd = useCallback(() => {
    setDragIndex(null);
    setOverIndex(null);
  }, []);

  return (
    <div ref={menuRef} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 rounded-lg border border-white/[0.08] bg-surface-raised px-3 py-1.5 text-xs font-medium text-white/60 transition-colors hover:border-white/[0.15] hover:text-white/80"
      >
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <rect x="3" y="3" width="7" height="7" />
          <rect x="14" y="3" width="7" height="7" />
          <rect x="3" y="14" width="7" height="7" />
          <rect x="14" y="14" width="7" height="7" />
        </svg>
        Layout
      </button>

      {open && (
        <div className="absolute left-0 top-full z-50 mt-2 w-72 rounded-xl border border-white/[0.08] bg-surface-raised p-2 shadow-xl">
          <p className="mb-1 px-2 py-1 text-[11px] uppercase tracking-wider text-white/30">
            Drag to reorder
          </p>
          {sections.map((section, i) => (
            <div
              key={section.id}
              draggable
              onDragStart={() => handleDragStart(i)}
              onDragOver={(e) => handleDragOver(e, i)}
              onDrop={() => handleDrop(i)}
              onDragEnd={handleDragEnd}
              className={`flex cursor-grab items-center gap-2 rounded-lg px-2 py-2 transition-colors active:cursor-grabbing ${
                dragIndex === i
                  ? "opacity-40"
                  : overIndex === i
                    ? "bg-white/[0.08]"
                    : "hover:bg-white/[0.04]"
              }`}
            >
              {/* Drag handle */}
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="currentColor"
                className="shrink-0 text-white/20"
              >
                <circle cx="9" cy="5" r="1.5" />
                <circle cx="15" cy="5" r="1.5" />
                <circle cx="9" cy="12" r="1.5" />
                <circle cx="15" cy="12" r="1.5" />
                <circle cx="9" cy="19" r="1.5" />
                <circle cx="15" cy="19" r="1.5" />
              </svg>

              {/* Checkbox */}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  toggle(section.id);
                }}
                className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors ${
                  section.visible
                    ? "border-blue-500 bg-blue-500"
                    : "border-white/20 bg-transparent"
                }`}
              >
                {section.visible && (
                  <svg
                    width="10"
                    height="10"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="white"
                    strokeWidth="3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                )}
              </button>

              {/* Label */}
              <span
                className={`flex-1 text-xs ${
                  section.visible ? "text-white/80" : "text-white/30"
                }`}
              >
                {section.label}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
