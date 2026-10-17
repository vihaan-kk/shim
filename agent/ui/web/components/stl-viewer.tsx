"use client";

import { Suspense } from "react";
import { Canvas, useLoader } from "@react-three/fiber";
import { Bounds, Center, OrbitControls } from "@react-three/drei";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";

// Displays an STL from a URL the server resolved. It never recomputes geometry.
// CAD frame: X is ML, Y is AP, opening at z = 0, distal is +Z. Rotating +90°
// about X puts the opening at the top and the distal end at the bottom.
function Mesh({ url, color }: { url: string; color: string }) {
  const geometry = useLoader(STLLoader, url);
  return (
    <mesh geometry={geometry} rotation={[Math.PI / 2, 0, 0]}>
      <meshStandardMaterial color={color} roughness={0.75} metalness={0} />
    </mesh>
  );
}

export function StlViewer({
  url,
  color = "#d3ccc7",
  label,
}: {
  url: string;
  color?: string;
  label: string;
}) {
  return (
    <div className="relative h-full w-full" role="img" aria-label={label}>
      <Canvas camera={{ position: [0, 0, 320], fov: 35 }} dpr={[1, 2]}>
        <color attach="background" args={["#f3f2ee"]} />
        <ambientLight intensity={0.7} />
        <directionalLight position={[120, 200, 160]} intensity={1.1} />
        <directionalLight position={[-160, -80, -120]} intensity={0.35} />
        <Suspense fallback={null}>
          <Bounds fit clip observe margin={1.15}>
            <Center>
              <Mesh url={url} color={color} />
            </Center>
          </Bounds>
        </Suspense>
        <OrbitControls makeDefault enablePan={false} />
      </Canvas>
    </div>
  );
}
