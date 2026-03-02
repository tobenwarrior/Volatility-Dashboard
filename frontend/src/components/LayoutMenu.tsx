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

const ITEM_H = 36;

export default function LayoutMenu({ sections, onChange }: LayoutMenuProps) {
  const [open, setOpen] = useState(false);
  const [dragId, setDragId] = useState<string | null>(null);
  const [dragY, setDragY] = useState(0);
  const menuRef = useRef<HTMLDivElement>(null);
  const itemEls = useRef(new Map<string, HTMLDivElement>());
  const flipTops = useRef(new Map<string, number>());
  const startY = useRef(0);
  const startIdx = useRef(0);

  // Refs to avoid stale closures in document listeners
  const sectionsRef = useRef(sections);
  sectionsRef.current = sections;
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const dragIdRef = useRef<string | null>(null);
  useEffect(() => { dragIdRef.current = dragId; }, [dragId]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const toggle = (id: string) => {
    onChange(sections.map((s) => (s.id === id ? { ...s, visible: !s.visible } : s)));
  };

  // Capture true layout positions for FLIP (clear in-flight transitions first)
  const capturePositions = useCallback(() => {
    const m = new Map<string, number>();
    itemEls.current.forEach((el, id) => {
      if (id === dragIdRef.current) return;
      el.style.transition = "none";
      el.style.transform = "none";
      void el.offsetHeight;
      m.set(id, el.getBoundingClientRect().top);
    });
    flipTops.current = m;
  }, []);

  // FLIP: animate non-dragged items from old position to new
  useLayoutEffect(() => {
    const prev = flipTops.current;
    if (prev.size === 0) return;
    flipTops.current = new Map();

    itemEls.current.forEach((el, id) => {
      if (id === dragIdRef.current) return;
      const oldTop = prev.get(id);
      if (oldTop === undefined) return;
      el.style.transition = "none";
      el.style.transform = "none";
      void el.offsetHeight;
      const newTop = el.getBoundingClientRect().top;
      const delta = oldTop - newTop;
      if (Math.abs(delta) < 1) return;
      el.style.transform = `translateY(${delta}px)`;
      void el.offsetHeight;
      el.style.transition = "transform 150ms ease-out";
      el.style.transform = "translateY(0)";
    });
  }, [sections]);

  // Pointer down on drag handle
  const handlePointerDown = useCallback((e: React.PointerEvent, idx: number, id: string) => {
    e.preventDefault();
    setDragId(id);
    setDragY(0);
    startY.current = e.clientY;
    startIdx.current = idx;
  }, []);

  // Document-level pointer tracking during drag
  useEffect(() => {
    if (dragId === null) return;

    const onMove = (e: PointerEvent) => {
      const id = dragIdRef.current;
      if (!id) return;

      const rawDy = e.clientY - startY.current;
      setDragY(rawDy);

      const secs = sectionsRef.current;
      const curIdx = secs.findIndex((s) => s.id === id);
      const targetIdx = Math.max(
        0,
        Math.min(secs.length - 1, startIdx.current + Math.round(rawDy / ITEM_H))
      );

      if (targetIdx !== curIdx) {
        capturePositions();
        const next = [...secs];
        const [moved] = next.splice(curIdx, 1);
        next.splice(targetIdx, 0, moved);
        onChangeRef.current(next);
        // Compensate so dragged item stays under pointer
        startY.current += (targetIdx - curIdx) * ITEM_H;
        startIdx.current = targetIdx;
        setDragY(e.clientY - startY.current);
      }
    };

    const onUp = () => {
      setDragId(null);
      setDragY(0);
    };

    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerup", onUp);
    return () => {
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerup", onUp);
    };
  }, [dragId, capturePositions]);

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
                style={
                  isDragging
                    ? { transform: `translateY(${dragY}px)`, zIndex: 10, position: "relative" }
                    : undefined
                }
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
                  onPointerDown={(e) => handlePointerDown(e, i, section.id)}
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
