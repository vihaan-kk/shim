"use client";

import { useEffect, useMemo } from "react";
import { useLoader } from "@react-three/fiber";
import { Html, Line, useBounds } from "@react-three/drei";
import { Matrix4, Vector3 } from "three";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { toCreasedNormals } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import type { SocketValidation } from "@/lib/types";
import { SocketSectionAnnotations } from "@/components/socket-section-annotations";
import { createLimbContour } from "@/lib/limb-contour";
import { LimbSkinMaterial } from "@/components/limb-skin-material";
import { SocketShellMaterial } from "@/components/socket-shell-material";

export function SocketLimbAssembly({ socketUrl, limbUrl, lowerLegUrl, showLowerLeg = false, engravingUrl, showLimb, insertion, revealInterior, measuredGeometry, measurements, onSize }: {
  socketUrl: string;
  limbUrl: string;
  // Adapter, pylon and foot under the socket: display only, never printed.
  lowerLegUrl?: string;
  showLowerLeg?: boolean;
  // Engraved label letters (removed material), drawn highlighted over the recess.
  engravingUrl?: string;
  showLimb: boolean;
  insertion: number;
  revealInterior: boolean;
  measuredGeometry: boolean;
  measurements?: SocketValidation["measurements"];
  onSize: (size: { length: number; width: number }) => void;
}) {
  // Load the optional files only when given; each keeps its own slot in the result.
  const loaded = useLoader(STLLoader, [socketUrl, limbUrl, lowerLegUrl, engravingUrl].filter((u): u is string => Boolean(u)));
  const [socket, limb] = loaded;
  const lowerLeg = lowerLegUrl ? loaded[2] : undefined;
  const engraving = engravingUrl ? loaded[lowerLegUrl ? 3 : 2] : undefined;
  const bounds = useBounds();
  const display = useMemo(() => {
    // Use the SAME limb-relative curve for both meshes. Deriving a separate
    // curve from the socket width would change the seated relationship.
    limb.computeBoundingBox();
    const reference = limb.boundingBox!;
    const renderCopy = (source: typeof limb) => {
      if (!measuredGeometry) return createLimbContour(source, reference);
      const copy = source.clone();
      const result = toCreasedNormals(copy, Math.PI / 3);
      if (result !== copy) copy.dispose();
      result.computeBoundingBox();
      return result;
    };
    const limbDisplay = renderCopy(limb);
    const socketDisplay = renderCopy(socket);
    const box = socketDisplay.boundingBox!;
    const limbBox = limbDisplay.boundingBox!;
    const size = box.getSize(new Vector3());
    const center = box.getCenter(new Vector3());
    const travel = limbBox.max.z - box.min.z + size.z * 0.15;
    // Fit the complete motion envelope once per mesh revision, never on toggles.
    const envelope = box.clone().union(limbBox).union(limbBox.clone().translate(new Vector3(0, 0, -travel)));
    const transform = new Matrix4().makeRotationX(Math.PI / 2)
      .multiply(new Matrix4().makeTranslation(-center.x, -center.y, -center.z));
    envelope.applyMatrix4(transform);
    return { limb: limbDisplay, socket: socketDisplay, box, limbBox, size, center, travel, envelope, transform };
  }, [socket, limb, measuredGeometry]);

  // The lower leg hangs from the socket's displayed closed end (its file starts at the
  // CAD socket depth), so it also lines up with the smoothed, unmeasured socket.
  const leg = useMemo(() => {
    if (!lowerLeg) return null;
    lowerLeg.computeBoundingBox();
    const legBox = lowerLeg.boundingBox!;
    const drop = display.box.max.z - legBox.min.z;
    return { geometry: lowerLeg, drop, box: legBox.clone().translate(new Vector3(0, 0, drop)) };
  }, [lowerLeg, display]);

  // Refit when the leg is shown or hidden; the limb's motion still never refits.
  useEffect(() => {
    const legShown = Boolean(leg && showLowerLeg);
    const envelope = display.envelope.clone();
    let length = display.size.z;
    if (legShown && leg) {
      envelope.union(leg.box.clone().applyMatrix4(display.transform));
      length += 2 * (leg.box.max.z - display.box.max.z); // the floor sits under the foot
    }
    onSize({ length, width: display.size.x });
    bounds.refresh(envelope).clip().fit();
  }, [display, leg, showLowerLeg, bounds, onSize]);

  useEffect(() => () => {
    display.limb.dispose();
    display.socket.dispose();
  }, [display]);

  const depth = measurements?.units === "mm" ? measurements.depth_mm : undefined;
  const offset = -display.travel * (1 - insertion / 100);
  return (
    <group rotation={[Math.PI / 2, 0, 0]}>
      <group position={[-display.center.x, -display.center.y, -display.center.z]}>
        <group visible={showLimb} position={[0, 0, offset]}>
          <mesh geometry={display.limb}>
            <LimbSkinMaterial />
          </mesh>
          {showLimb && insertion < 100 && (
            <Html position={[display.limbBox.max.x + 10, 0, display.limbBox.min.z]}>
              <span className="block w-28 rounded border bg-background/95 px-2 py-1 text-xs">Confirmed residual-limb model</span>
            </Html>
          )}
        </group>
        {leg && (
          <mesh geometry={leg.geometry} position={[0, 0, leg.drop]} visible={showLowerLeg}>
            <meshStandardMaterial color="#a8a29e" metalness={0.35} roughness={0.45} />
          </mesh>
        )}
        {leg && showLowerLeg && (
          <Html position={[leg.box.max.x + 10, 0, (leg.box.min.z + leg.box.max.z) / 2]}>
            <span className="block w-32 rounded border bg-background/95 px-2 py-1 text-xs">Adapter, pylon and foot · visualization only, not printed</span>
          </Html>
        )}
        {/* Only in the measured view: the smoothed contour moves the wall away from the letters. */}
        {engraving && measuredGeometry && engraving.getAttribute("position").count > 0 && (
          <mesh geometry={engraving} renderOrder={2}>
            <meshStandardMaterial color="#ea580c" emissive="#ea580c" emissiveIntensity={0.35}
              polygonOffset polygonOffsetFactor={-2} polygonOffsetUnits={-2} />
          </mesh>
        )}
        <mesh geometry={display.socket} renderOrder={revealInterior ? 1 : 0}>
          <SocketShellMaterial box={display.box} revealInterior={revealInterior} />
        </mesh>
        {measuredGeometry && typeof depth === "number" && Number.isFinite(depth) && (
          <>
            <Line points={[[display.box.min.x - 12, 0, 0], [display.box.min.x - 12, 0, depth]]} color="#57534e" lineWidth={1} />
            <Html position={[display.box.min.x - 18, 0, depth / 2]} center>
              <span className="block whitespace-nowrap rounded-full border bg-background/95 px-2 py-1 text-[11px]">{depth.toFixed(1)} mm</span>
            </Html>
          </>
        )}
        {measuredGeometry && <SocketSectionAnnotations geometry={display.socket} measurements={measurements} />}

      </group>
    </group>
  );
}
