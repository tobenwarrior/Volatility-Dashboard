"use client";

import { useState, useRef, useEffect, useCallback, useLayoutEffect } from "react";

export type Section = {
  id: string;
  label: string;
  visible: boolean;
};

interface LayoutMenuProps {
  sections: Section[];
  onChange: (sections: Section[]) => void;
}

const ITEM_H = 36; // row height in px (py-2 + content)

export default function LayoutMenu({ sections, onChange }: LayoutMenuProps) {
  const [open, setOpen] = useState(false);
  const [dragId, setDragId] = useState<string | null>(null);
  const [dragOffset, setDragOffset] = useState(0);
  const menuRef = useRef<HTMLDivElement>(null);
  const itemEls = useRef<Map<string, HTMLDivElement>>(new Map());
  const prevRects = useRef<Map<string, number>>(new Map());
  const originY = useRef(0);
  const originIdx = useRef(0);

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

  // Snapshot Y positions before reorder
  const snapshot = useCallback(() => {
    const m = new Map<string, number>();
    itemEls.current.forEach((el, id) => m.set(id, el.getBoundingClientRect().top));
    prevRects.current = m;
  }, []);

  // FLIP: animate non-dragged items from old → new position
  useLayoutEffect(() => {
    const prev = prevRects.current;
    if (prev.size === 0) return;

    itemEls.current.forEach((el, id) => {
      if (id === dragId) return;
      const oldTop = prev.get(id);
      if (oldTop === undefined) return;
      const newTop = el.getBoundingClientRect().top;
      const dy = oldTop - newTop;
      if (Math.abs(dy) < 1) return;

      el.style.transform = `translateY(${dy}px)`;
      el.style.transition = "none";
      void el.offsetHeight; // force reflow
      el.style.transform = "";
      el.style.transition = "transform 150ms ease-out";
    });

    prevRects.current = new Map();
  }, [sections, dragId]);

  // Pointer-based drag
  const onPointerDown = useCallback(
    (e: React.PointerEvent, idx: number, id: string) => {
      e.preventDefault();
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
      setDragId(id);
      setDragOffset(0);
      originY.current = e.clientY;
      originIdx.current = idx;
    },
    []
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (dragId === null) return;
      const dy = e.clientY - originY.current;
      setDragOffset(dy);

      const curIdx = sections.findIndex((s) => s.id === dragId);
      const newIdx = Math.max(
        0,
        Math.min(sections.length - 1, originIdx.current + Math.round(dy / ITEM_H))
      );
      if (newIdx !== curIdx) {
        snapshot();
        const next = [...sections];
        const [moved] = next.splice(curIdx, 1);
        next.splice(newIdx, 0, moved);
        onChange(next);
        // Adjust origin so offset stays consistent after reorder
        originY.current += (newIdx - curIdx) * ITEM_H;
        setDragOffset(e.clientY - originY.current);
      }
    },
    [dragId, sections, onChange, snapshot]
  );

  const onPointerUp = useCallback(() => {
    setDragId(null);
    setDragOffset(0);
  }, []);

  const setItemRef = useCallback((id: string, el: HTMLDivElement | null) => {
    if (el) itemEls.current.set(id, el);
    else itemEls.current.delete(id);
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
        Order
      </button>

      {open && (
        <div className="absolute left-0 top-full z-50 mt-2 w-72 rounded-xl border border-white/[0.08] bg-surface-raised p-2 shadow-xl">
          <p className="mb-1 px-2 py-1 text-[11px] uppercase tracking-wider text-white/30">
            Drag to reorder
          </p>
          {sections.map((section, i) => {
            const isDragging = dragId === section.id;
            return (
              <div
                key={section.id}
                ref={(el) => setItemRef(section.id, el)}
                onPointerMove={onPointerMove}
                onPointerUp={onPointerUp}
                style={isDragging ? { transform: `translateY(${dragOffset}px)`, zIndex: 10 } : undefined}
                className={`flex select-none items-center gap-2 rounded-lg px-2 py-2 ${
                  isDragging
                    ? "scale-[1.02] bg-white/[0.08] shadow-lg"
                    : "hover:bg-white/[0.04]"
                }`}
              >
                {/* Drag handle */}
                <svg
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                  className="shrink-0 cursor-grab text-white/20 active:cursor-grabbing"
                  onPointerDown={(e) => onPointerDown(e, i, section.id)}
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
            );
          })}
        </div>
      )}
    </div>
  );
}
