import * as THREE from "three";
import { toCreasedNormals } from "three/examples/jsm/utils/BufferGeometryUtils.js";

// Gentle centerline sweep, shared by the standalone limb and socket assembly.
export function limbSectionOffset(z: number, box: THREE.Box3): THREE.Vector2 {
  const length = box.max.z - box.min.z;
  if (length <= 0) return new THREE.Vector2();
  const t = THREE.MathUtils.clamp((z - box.min.z) / length, 0, 1);
  const width = box.max.x - box.min.x;
  // A small, one-direction sweep retains the source's below-knee taper.
  // Avoid a central bulge or reversing bend that reads as a knee joint.
  const sweep = t * t * (3 - 2 * t);
  return new THREE.Vector2(
    width * 0.025 * sweep,
    width * 0.015 * sweep,
  );
}

// Shape only the terminal section below the form's distal measurement station.
// This blends into the existing rounded cap instead of leaving a broad,
// flat-looking end. The P/M/D measurement planes and axial length stay fixed.
export function limbTipScale(z: number, box: THREE.Box3): number {
  const length = box.max.z - box.min.z;
  if (length <= 0) return 1;
  const tipZone = Math.min(40, length - 40, length * 0.4);
  if (tipZone <= 0) return 1;
  const t = THREE.MathUtils.clamp((z - (box.max.z - tipZone)) / tipZone, 0, 1);
  return 1 - 0.28 * t * t;
}

export function createLimbContour(source: THREE.BufferGeometry, referenceBox?: THREE.Box3): THREE.BufferGeometry {
  const copy = source.clone();
  copy.computeBoundingBox();
  const box = referenceBox ?? copy.boundingBox!;
  const center = box.getCenter(new THREE.Vector3());
  const positions = copy.getAttribute("position");
  for (let i = 0; i < positions.count; i++) {
    const offset = limbSectionOffset(positions.getZ(i), box);
    const scale = limbTipScale(positions.getZ(i), box);
    positions.setXY(i,
      center.x + (positions.getX(i) - center.x) * scale + offset.x,
      center.y + (positions.getY(i) - center.y) * scale + offset.y,
    );
  }
  positions.needsUpdate = true;
  // Smooth the curved sides while retaining the proximal cap's sharp rim.
  const result = toCreasedNormals(copy, Math.PI / 3);
  if (result !== copy) copy.dispose();
  result.computeBoundingBox();
  result.computeBoundingSphere();
  return result;
}
