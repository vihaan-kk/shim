"use client";

import { useMemo } from "react";
import { Html, Line } from "@react-three/drei";
import type { BufferGeometry } from "three";
import type { SocketValidation } from "@/lib/types";

const NAMES: Record<string, string> = { proximal: "Opening", q25: "Upper", q50: "Middle", q75: "Lower", distal_reference: "Distal" };
const labelStyle = { background: "rgba(255,255,255,0.94)", border: "1px solid #d6d3d1", borderRadius: 999, color: "#292524", fontSize: 11, lineHeight: 1.3, padding: "3px 7px", whiteSpace: "nowrap" as const, pointerEvents: "none" as const };

// Intersect rendered triangles with a reported section plane solely to draw
// its annotation. Circumference values always come from the backend report.
export function SocketSectionAnnotations({ geometry, measurements }: {
  geometry: BufferGeometry;
  measurements?: SocketValidation["measurements"];
}) {
  const sections = useMemo(() => {
    if (measurements?.units !== "mm") return [];
    const positions = geometry.getAttribute("position");
    const index = geometry.index;
    const count = index?.count ?? positions.count;
    return (measurements.sections ?? []).filter(row => row.status === "measured" && Number.isFinite(row.z_mm) && Number.isFinite(row.outer_perimeter_mm)).map(row => {
      const segments: [number, number, number][] = [];
      let maxX = -Infinity;
      for (let i = 0; i < count; i += 3) {
        const ids = [0, 1, 2].map(n => index ? index.getX(i + n) : i + n);
        const hits: [number, number, number][] = [];
        for (let edge = 0; edge < 3; edge++) {
          const a = ids[edge], b = ids[(edge + 1) % 3];
          const za = positions.getZ(a), zb = positions.getZ(b);
          if ((za <= row.z_mm && zb > row.z_mm) || (zb <= row.z_mm && za > row.z_mm)) {
            const t = (row.z_mm - za) / (zb - za);
            hits.push([positions.getX(a) + t * (positions.getX(b) - positions.getX(a)), positions.getY(a) + t * (positions.getY(b) - positions.getY(a)), row.z_mm]);
          }
        }
        if (hits.length === 2) {
          segments.push(...hits);
          maxX = Math.max(maxX, hits[0][0], hits[1][0]);
        }
      }
      return { row, segments, maxX };
    });
  }, [geometry, measurements]);
  return <>{sections.map(({ row, segments, maxX }) => segments.length > 0 && (
    <group key={row.id}>
      <Line points={segments} segments color="#44403c" lineWidth={1.5} depthTest={false} renderOrder={2} />
      <Html position={[maxX + 8, 0, row.z_mm]} center style={labelStyle}>
        {NAMES[row.id] ?? row.id} · {row.outer_perimeter_mm.toFixed(1)} mm
      </Html>
    </group>
  ))}</>;
}
