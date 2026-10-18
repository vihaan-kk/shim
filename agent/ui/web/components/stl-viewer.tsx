"use client";

import { Suspense, useEffect, useMemo, useState, type CSSProperties } from "react";
import * as THREE from "three";
import { Canvas, useLoader } from "@react-three/fiber";
import {
  Bounds,
  Center,
  ContactShadows,
  GizmoHelper,
  GizmoViewport,
  Html,
  Line,
  OrbitControls,
} from "@react-three/drei";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { toCreasedNormals } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { LimbSkinMaterial } from "@/components/limb-skin-material";
import { SocketShellMaterial } from "@/components/socket-shell-material";
import type { SocketValidation } from "@/lib/types";
import { SocketLimbAssembly } from "@/components/socket-limb-assembly";
import { createLimbContour, limbSectionOffset, limbTipScale } from "@/lib/limb-contour";

// One measurement station to draw on the model: a ring at zMm from the
// proximal (opening) end, labelled with its circumference when known.
export interface ViewerStation {
  label: string;
  zMm: number;
  circumferenceMm?: number | null;
}

export interface ViewerAnnotations {
  lengthMm?: number | null;
  stations?: ViewerStation[];
}

const INK = "#44403c";
const FAINT = "#a8a29e";

const LABEL_STYLE: CSSProperties = {
  background: "rgba(255,255,255,0.88)",
  border: "1px solid #d6d3d1",
  borderRadius: 999,
  color: "#292524",
  fontSize: 11,
  lineHeight: 1,
  padding: "3px 7px",
  pointerEvents: "none",
  whiteSpace: "nowrap",
};

type Vec3 = [number, number, number];

function ellipsePoints(cx: number, cy: number, z: number, rx: number, ry: number): Vec3[] {
  return Array.from({ length: 65 }, (_, i) => {
    const t = (i / 64) * Math.PI * 2;
    return [cx + rx * Math.cos(t), cy + ry * Math.sin(t), z];
  });
}

// Displays an STL from a URL the server resolved. The optional skin treatment
// bends a private display copy; source STL and cross-section sizes stay intact.
// Annotation rings follow the same centerline as that display copy.
// CAD frame: X is ML, Y is AP, opening at z = 0, distal is +Z. Rotating +90°
// about X puts the opening at the top and the distal end at the bottom.
// Annotations are drawn in the same CAD frame, inside the rotated group.
function Model({
  url,
  color,
  skin,
  shell,
  annotations,
  onSize,
}: {
  url: string;
  color: string;
  skin: boolean;
  shell: boolean;
  annotations?: ViewerAnnotations;
  onSize: (size: { length: number; width: number }) => void;
}) {
  const geometry = useLoader(STLLoader, url);
  const displayGeometry = useMemo(() => {
    if (skin) return createLimbContour(geometry);
    if (shell) {
      const copy = geometry.clone();
      const smoothed = toCreasedNormals(copy, Math.PI / 3);
      if (smoothed !== copy) copy.dispose();
      return smoothed;
    }
    return geometry;
  }, [geometry, skin, shell]);

  useEffect(() => () => {
    if (displayGeometry !== geometry) displayGeometry.dispose();
  }, [displayGeometry, geometry]);

  const info = useMemo(() => {
    geometry.computeBoundingBox();
    const box = geometry.boundingBox ?? new THREE.Box3();
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const position = geometry.attributes.position;

    // Semi-axes of the mesh cross-section at a given z, from the vertices
    // near that plane. Falls back to the widest section if none are close.
    const radiiAt = (zTarget: number) => {
      let rx = 0;
      let ry = 0;
      for (let band = 2; band <= 8 && rx === 0; band *= 2) {
        for (let i = 0; i < position.count; i++) {
          if (Math.abs(position.getZ(i) - zTarget) <= band) {
            rx = Math.max(rx, Math.abs(position.getX(i) - center.x));
            ry = Math.max(ry, Math.abs(position.getY(i) - center.y));
          }
        }
      }
      if (rx === 0) return { rx: size.x / 2, ry: size.y / 2 };
      return { rx: rx * 1.02 + 0.6, ry: ry * 1.02 + 0.6 };
    };

    return { box, size, center, radiiAt };
  }, [geometry]);

  useEffect(() => {
    onSize({ length: info.size.z, width: info.size.x });
  }, [info, onSize]);

  const { box, size, center } = info;
  const stations = annotations?.stations ?? [];
  const lengthLabel = Math.round(annotations?.lengthMm ?? size.z);
  // Dimension line for the length, offset to the left of the model.
  const dimX = center.x - size.x / 2 - 20;

  return (
    <group rotation={[Math.PI / 2, 0, 0]}>
      <mesh geometry={displayGeometry}>
        {skin ? <LimbSkinMaterial /> : shell ? <SocketShellMaterial box={box} /> : <meshStandardMaterial color={color} roughness={0.75} metalness={0} />}
      </mesh>

      {stations.map((station) => {
        const z = box.min.z + station.zMm;
        const radii = info.radiiAt(z);
        const scale = skin ? limbTipScale(z, box) : 1;
        const rx = radii.rx * scale;
        const ry = radii.ry * scale;
        const offset = skin ? limbSectionOffset(z, box) : new THREE.Vector2();
        const cx = center.x + offset.x;
        const cy = center.y + offset.y;
        const text =
          station.circumferenceMm != null
            ? `${station.label} · ${Math.round(station.circumferenceMm)} mm`
            : station.label;
        return (
          <group key={station.label}>
            <Line points={ellipsePoints(cx, cy, z, rx, ry)} color={INK} lineWidth={1.5} />
            <Html position={[cx + rx + 7, cy, z]} center style={LABEL_STYLE}>
              {text}
            </Html>
          </group>
        );
      })}

      {annotations?.lengthMm !== null && annotations !== undefined && (
        <group>
          <Line
            points={[
              [dimX, center.y, box.min.z],
              [dimX, center.y, box.max.z],
            ]}
            color={FAINT}
            lineWidth={1}
          />
          <Line
            points={[
              [dimX - 4, center.y, box.min.z],
              [dimX + 4, center.y, box.min.z],
            ]}
            color={FAINT}
            lineWidth={1}
          />
          <Line
            points={[
              [dimX - 4, center.y, box.max.z],
              [dimX + 4, center.y, box.max.z],
            ]}
            color={FAINT}
            lineWidth={1}
          />
          <Html position={[dimX - 8, center.y, (box.min.z + box.max.z) / 2]} center style={LABEL_STYLE}>
            {lengthLabel} mm
          </Html>
        </group>
      )}
    </group>
  );
}

export function StlViewer({
  url,
  color = "#d3ccc7",
  skin = false,
  shell = false,
  limbUrl,
  showLimb = true,
  insertion = 0,
  revealInterior = false,
  measuredGeometry = false,
  socketMeasurements,
  label,
  annotations,
}: {
  url: string;
  color?: string;
  skin?: boolean;
  shell?: boolean;
  limbUrl?: string;
  showLimb?: boolean;
  insertion?: number;
  revealInterior?: boolean;
  measuredGeometry?: boolean;
  socketMeasurements?: SocketValidation["measurements"];
  label: string;
  annotations?: ViewerAnnotations;
}) {
  const [info, setInfo] = useState<{ length: number; width: number } | null>(null);
  // The model is centred on the origin, standing along world Y, so its
  // underside sits half its length below the centre.
  const floorY = info ? -info.length / 2 - 1 : -80;
  const floorSize = info ? Math.max(info.length, info.width) * 2.2 : 320;

  return (
    <div className="relative h-full w-full" role="img" aria-label={label}>
      <Canvas camera={{ position: shell ? [60, 65, 320] : [0, 0, 320], fov: 35 }} dpr={[1, 2]}>
        <color attach="background" args={["#f3f2ee"]} />
        <ambientLight intensity={skin ? 0.45 : 0.7} />
        <directionalLight position={skin ? [-140, 180, 170] : [120, 200, 160]} intensity={skin ? 1.65 : 1.1} />
        <directionalLight position={[-160, -80, -120]} intensity={0.35} />
        {skin && <directionalLight position={[160, 50, -100]} intensity={0.7} color="#ffe6ce" />}
        <Suspense fallback={null}>
          {shell && limbUrl ? (
            <Bounds margin={1.25} maxDuration={0}>
              <SocketLimbAssembly socketUrl={url} limbUrl={limbUrl} showLimb={showLimb} insertion={insertion} revealInterior={revealInterior} measuredGeometry={measuredGeometry} measurements={socketMeasurements} onSize={setInfo} />
            </Bounds>
          ) : (
            <Bounds fit clip observe margin={1.15}>
              <Center>
                <Model url={url} color={color} skin={skin} shell={shell} annotations={annotations} onSize={setInfo} />
              </Center>
            </Bounds>
          )}
        </Suspense>
        {info && (
          <>
            {/* Plain line grids, not drei's shader Grid: that material fades
                lines by distance in world units (invisible at mm scale) and
                discards them at some angles. GridHelpers always render, from
                every side. Fine grid: 10 mm cells; coarse: 50 mm sections. */}
            <gridHelper
              args={[4000, 400, "#a8a29e", "#d6d3d1"]}
              position={[0, floorY, 0]}
              material-transparent
              material-opacity={0.55}
            />
            <gridHelper
              args={[4000, 80, "#78716c", "#a8a29e"]}
              position={[0, floorY + 0.1, 0]}
              material-transparent
              material-opacity={0.8}
            />
            <ContactShadows
              position={[0, floorY + 0.5, 0]}
              scale={floorSize * 0.7}
              far={info.length * 1.05}
              blur={2.2}
              opacity={0.32}
              resolution={512}
            />
          </>
        )}
        <OrbitControls makeDefault enablePan={false} />
        <GizmoHelper alignment="bottom-right" margin={[64, 64]}>
          <GizmoViewport axisColors={["#b45309", "#57534e", "#334155"]} labelColor="#292524" />
        </GizmoHelper>
      </Canvas>
    </div>
  );
}
