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

export function SocketLimbAssembly({ socketUrl, limbUrl, showLimb, insertion, revealInterior, measuredGeometry, measurements, onSize }: {
  socketUrl: string;
  limbUrl: string;
  showLimb: boolean;
  insertion: number;
  revealInterior: boolean;
  measuredGeometry: boolean;
  measurements?: SocketValidation["measurements"];
  onSize: (size: { length: number; width: number }) => void;
}) {
  const [socket, limb] = useLoader(STLLoader, [socketUrl, limbUrl]);
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
    return { limb: limbDisplay, socket: socketDisplay, box, limbBox, size, center, travel, envelope };
  }, [socket, limb, measuredGeometry]);

  useEffect(() => {
    onSize({ length: display.size.z, width: display.size.x });
    bounds.refresh(display.envelope).clip().fit();
  }, [display, bounds, onSize]);

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
