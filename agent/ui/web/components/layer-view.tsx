"use client";

import { useEffect, useMemo } from "react";
import * as THREE from "three";
import { Canvas } from "@react-three/fiber";
import { Bounds, Line, OrbitControls } from "@react-three/drei";
import { useSession } from "@/lib/session";
import type { PrintLayers } from "@/lib/types";

const PRINTED = new THREE.Color("#44403c");
const UPCOMING = new THREE.Color("#cfc9c2");
const CURRENT = "#ea580c";

type Vec3 = [number, number, number];

// All outer-wall paths as one set of line segments, centred on the part, with
// the layer of each vertex kept so the colours can follow the current layer.
function useLayerGeometry(data: PrintLayers) {
  return useMemo(() => {
    const positions: number[] = [];
    const layerOf: number[] = [];
    data.layers.forEach((layer, index) => {
      for (const path of layer.paths) {
        for (let i = 0; i + 3 < path.length; i += 2) {
          positions.push(path[i], path[i + 1], layer.z, path[i + 2], path[i + 3], layer.z);
          layerOf.push(index + 1, index + 1);
        }
      }
    });
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    geometry.setAttribute("color", new THREE.Float32BufferAttribute(new Float32Array(positions.length), 3));
    geometry.computeBoundingBox();
    const center = geometry.boundingBox!.getCenter(new THREE.Vector3());
    return { geometry, layerOf, center };
  }, [data]);
}

function Layers({ data, current }: { data: PrintLayers; current: number | null }) {
  const { geometry, layerOf, center } = useLayerGeometry(data);

  // Recolour on every new layer: printed below, upcoming faint above.
  useEffect(() => {
    const colors = geometry.getAttribute("color") as THREE.BufferAttribute;
    layerOf.forEach((layer, i) => {
      const c = current != null && layer <= current ? PRINTED : UPCOMING;
      colors.setXYZ(i, c.r, c.g, c.b);
    });
    colors.needsUpdate = true;
  }, [geometry, layerOf, current]);

  useEffect(() => () => geometry.dispose(), [geometry]);

  // A support-only layer has no wall; highlight the last layer at or below it that has one.
  const currentPaths = useMemo(() => {
    let index = current != null ? Math.min(current, data.layers.length) - 1 : -1;
    while (index >= 0 && data.layers[index].paths.length === 0) index -= 1;
    const layer = index >= 0 ? data.layers[index] : undefined;
    if (!layer) return [];
    return layer.paths.map((path) => {
      const points: Vec3[] = [];
      for (let i = 0; i + 1 < path.length; i += 2) points.push([path[i], path[i + 1], layer.z]);
      return points;
    });
  }, [data, current]);

  // G-code is Z-up on the bed; three.js is Y-up.
  return (
    <group rotation={[-Math.PI / 2, 0, 0]}>
      <group position={[-center.x, -center.y, -center.z]}>
        <lineSegments geometry={geometry}>
          <lineBasicMaterial vertexColors />
        </lineSegments>
        {currentPaths.map((points, i) => (
          <Line key={i} points={points} color={CURRENT} lineWidth={2.5} />
        ))}
      </group>
    </group>
  );
}

// README §12: the layer comes from OctoPrint's filepos in the job's own G-code,
// never from an estimate. Link loss keeps the last reported layer, marked stale.
export function LayerView() {
  const { layers, snapshot, started } = useSession();

  if (!started) return null;
  if (!layers) {
    return (
      <div className="grid gap-1 rounded-md border border-dashed p-6">
        <span className="eyebrow">Live layer view</span>
        <p className="text-sm text-muted-foreground">
          Needs the job&apos;s G-code from the real slicer. The fake printer has none.
        </p>
      </div>
    );
  }

  const current = snapshot?.layer ?? null;
  const caption =
    current == null
      ? "Waiting for the printer to reach the first layer"
      : `Layer ${current} of ${layers.layer_count} · Z ${snapshot?.layer_z?.toFixed(2)} mm`;

  return (
    <div className="grid gap-2">
      <div className="flex items-baseline justify-between gap-3">
        <span className="eyebrow">Live layer view</span>
        <span className={snapshot?.stale ? "text-xs text-destructive" : "text-xs text-muted-foreground"}>
          {snapshot?.stale ? `Link lost · last reported: ${caption}` : caption}
        </span>
      </div>
      <div
        className="h-[360px] overflow-hidden rounded-md border"
        role="img"
        aria-label={`Outer walls of the sliced part, ${caption.toLowerCase()}`}
      >
        <Canvas camera={{ position: [140, 110, 180], fov: 35 }} dpr={[1, 2]}>
          <color attach="background" args={["#f3f2ee"]} />
          <Bounds fit clip margin={1.2}>
            <Layers data={layers} current={current} />
          </Bounds>
          <OrbitControls makeDefault />
        </Canvas>
      </div>
      <p className="text-[11px] text-muted-foreground">
        Outer walls from the sliced file. Dark is printed, orange is the layer OctoPrint is on, light is still to
        print.
      </p>
    </div>
  );
}
