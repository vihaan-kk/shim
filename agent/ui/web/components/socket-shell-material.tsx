"use client";

import { useMemo } from "react";
import { Box3, Vector3, type MeshStandardMaterial } from "three";

export function SocketShellMaterial({ box, revealInterior = false }: { box: Box3; revealInterior?: boolean }) {
  const applyShell = useMemo<MeshStandardMaterial["onBeforeCompile"]>(() => (shader) => {
    shader.uniforms.shellCenter = { value: box.getCenter(new Vector3()) };
    shader.uniforms.shellMinZ = { value: box.min.z };
    shader.uniforms.shellLength = { value: Math.max(box.max.z - box.min.z, 1) };
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", `#include <common>
        varying vec3 vShellPosition;
        varying vec3 vShellNormal;`)
      .replace("#include <begin_vertex>", `#include <begin_vertex>
        vShellPosition = position;
        vShellNormal = normal;`);
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", `#include <common>
        varying vec3 vShellPosition;
        varying vec3 vShellNormal;
        uniform vec3 shellCenter;
        uniform float shellMinZ;
        uniform float shellLength;`)
      .replace("#include <color_fragment>", /* glsl */ `
        #include <color_fragment>
        vec2 radial = vShellPosition.xy - shellCenter.xy;
        vec2 direction = radial / max(length(radial), 0.001);
        float height = (vShellPosition.z - shellMinZ) / shellLength;
        // Integer repeats close the weave around the shell without a seam.
        vec2 weaveUV = vec2(atan(radial.y, radial.x) * 30.5577491, vShellPosition.z);
        vec2 cell = floor(weaveUV);
        vec2 local = fract(weaveUV);
        float over = step(2.0, mod(cell.x + cell.y, 4.0));
        float across = mix(local.x, local.y, over);
        float bundle = pow(max(sin(across * 3.14159265), 0.0), 0.55);
        float detail = 1.0 - smoothstep(0.3, 1.0, length(fwidth(weaveUV)));
        float fibers = sin(across * 50.26548) * 0.025 * detail;
        float weave = mix(0.5, bundle * mix(0.6, 1.0, over) + fibers, detail);
        vec3 carbon = mix(vec3(0.018, 0.022, 0.028), vec3(0.085, 0.095, 0.11), weave);
        // Pale inner surface and rim, plus an inset-looking front finish.
        // These are colors only: no liner, strap or structural geometry is added.
        float inside = 1.0 - smoothstep(-0.15, 0.15, dot(normalize(vShellNormal).xy, direction));
        float rim = 1.0 - smoothstep(0.025, 0.055, height);
        float panelWidth = 0.72 + 0.15 * pow(abs((height - 0.5) / 0.4), 4.0);
        float panel = smoothstep(panelWidth, panelWidth + 0.025, direction.y)
          * smoothstep(0.12, 0.17, height) * (1.0 - smoothstep(0.84, 0.91, height));
        float pale = max(max(inside, rim), panel);
        diffuseColor.rgb = mix(carbon, vec3(0.64, 0.69, 0.74), pale);
      `)
      .replace("#include <roughnessmap_fragment>", `#include <roughnessmap_fragment>
        roughnessFactor = mix(0.38 + weave * 0.12, 0.62, pale);`);
  }, [box]);

  return <meshStandardMaterial key={`${box.min.toArray()}-${box.max.toArray()}-${revealInterior}`} roughness={0.45} metalness={0.08} transparent={revealInterior} opacity={revealInterior ? 0.22 : 1} depthWrite={!revealInterior} onBeforeCompile={applyShell} />;
}
