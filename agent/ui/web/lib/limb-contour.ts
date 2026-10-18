import * as THREE from "three";
import { toCreasedNormals } from "three/examples/jsm/utils/BufferGeometryUtils.js";

// Translate whole transverse sections, never scale them: every circumference,
// AP/ML width and axial length is preserved. This is a display-only contour.
export function limbSectionOffset(z: number, box: THREE.Box3): THREE.Vector2 {
  const length = box.max.z - box.min.z;
  if (length <= 0) return new THREE.Vector2();
  const t = THREE.MathUtils.clamp((z - box.min.z) / length, 0, 1);
  const width = box.max.x - box.min.x;
  const arc = Math.sin(Math.PI * t) ** 2;
  return new THREE.Vector2(
    width * 0.085 * arc * Math.cos(Math.PI * (t - 0.2)),
    width * 0.055 * arc,
  );
}

export function createLimbContour(source: THREE.BufferGeometry): THREE.BufferGeometry {
  const copy = source.clone();
  copy.computeBoundingBox();
  const box = copy.boundingBox!;
  const positions = copy.getAttribute("position");
  for (let i = 0; i < positions.count; i++) {
    const offset = limbSectionOffset(positions.getZ(i), box);
    positions.setXY(i, positions.getX(i) + offset.x, positions.getY(i) + offset.y);
  }
  positions.needsUpdate = true;
  // Smooth the curved sides while retaining the proximal cap's sharp rim.
  const result = toCreasedNormals(copy, Math.PI / 3);
  if (result !== copy) copy.dispose();
  result.computeBoundingBox();
  result.computeBoundingSphere();
  return result;
}
