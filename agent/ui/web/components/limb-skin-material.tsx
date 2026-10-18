"use client";

import type { MeshStandardMaterial } from "three";

// Object-space noise wraps STL surfaces without UV seams, including the tip.
// Only the rendered material changes; exported geometry stays untouched.
const skinNoise = /* glsl */ `
  varying vec3 vSkinPosition;

  float skinHash(vec3 p) {
    p = fract(p * 0.1031);
    p += dot(p, p.yzx + 33.33);
    return fract((p.x + p.y) * p.z);
  }

  float skinNoise(vec3 p) {
    vec3 i = floor(p);
    vec3 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(
      mix(mix(skinHash(i), skinHash(i + vec3(1, 0, 0)), f.x),
          mix(skinHash(i + vec3(0, 1, 0)), skinHash(i + vec3(1, 1, 0)), f.x), f.y),
      mix(mix(skinHash(i + vec3(0, 0, 1)), skinHash(i + vec3(1, 0, 1)), f.x),
          mix(skinHash(i + vec3(0, 1, 1)), skinHash(i + vec3(1, 1, 1)), f.x), f.y), f.z);
  }
`;

const applySkin: MeshStandardMaterial["onBeforeCompile"] = (shader) => {
  shader.vertexShader = shader.vertexShader
    .replace("#include <common>", "#include <common>\nvarying vec3 vSkinPosition;")
    .replace("#include <begin_vertex>", "#include <begin_vertex>\nvSkinPosition = position;");
  shader.fragmentShader = shader.fragmentShader
    .replace("#include <common>", `#include <common>\n${skinNoise}`)
    .replace("#include <color_fragment>", /* glsl */ `
      #include <color_fragment>
      float mottling = skinNoise(vSkinPosition * 0.075) - 0.5;
      float grain = skinNoise(vSkinPosition * 2.4);
      // Fade fine detail at a distance to avoid shimmering while orbiting.
      float detail = 1.0 - smoothstep(0.35, 1.2, length(fwidth(vSkinPosition * 2.4)));
      float pores = smoothstep(0.62, 0.88, grain) * detail;
      diffuseColor.rgb *= 1.0 + mottling * 0.12 - pores * 0.09;
      diffuseColor.rgb += vec3(0.012, -0.003, -0.006) * mottling;
    `)
    .replace("#include <roughnessmap_fragment>", /* glsl */ `
      #include <roughnessmap_fragment>
      roughnessFactor = clamp(roughnessFactor + (grain - 0.5) * 0.12 * detail, 0.65, 0.95);
    `);
};

export function LimbSkinMaterial() {
  return <meshStandardMaterial color="#bc9980" roughness={0.82} metalness={0} onBeforeCompile={applySkin} />;
}
