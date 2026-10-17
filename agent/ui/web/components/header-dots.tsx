"use client";

import { useEffect, useRef } from "react";

// A quiet dot field in the spirit of the Optimus hero. Header only: the 3D
// viewers further down get the GPU to themselves. Static when the user prefers
// reduced motion.
export function HeaderDots({ className }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let frame = 0;
    let raf = 0;

    const resize = () => {
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = canvas.clientWidth * ratio;
      canvas.height = canvas.clientHeight * ratio;
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    };

    const draw = () => {
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      ctx.clearRect(0, 0, w, h);
      const gap = 14;
      const cx = w * 0.78;
      const cy = h * 0.5;
      for (let x = gap / 2; x < w; x += gap) {
        for (let y = gap / 2; y < h; y += gap) {
          const d = Math.hypot(x - cx, y - cy);
          const wave = Math.sin(d / 18 - frame / 40);
          const fade = Math.max(0, 1 - d / (w * 0.55));
          const alpha = fade * (0.18 + 0.22 * wave);
          if (alpha <= 0.02) continue;
          ctx.fillStyle = `rgba(8, 5, 3, ${alpha.toFixed(3)})`;
          const size = 1 + Math.max(0, wave) * 1.2;
          ctx.fillRect(x, y, size, size);
        }
      }
    };

    const loop = () => {
      frame += 1;
      draw();
      raf = requestAnimationFrame(loop);
    };

    resize();
    window.addEventListener("resize", resize);
    if (still) draw();
    else loop();

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return <canvas ref={ref} aria-hidden className={className} />;
}
