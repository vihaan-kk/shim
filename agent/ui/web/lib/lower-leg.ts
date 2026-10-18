// Display-only files served next to a socket's shell STL.
export function lowerLegUrl(socketStlUrl: string): string {
  return socketStlUrl.replace(/socket_shell\.stl$/, "lower_leg.stl");
}

// The engraved label's letters (empty for a socket without one).
export function engravingUrl(socketStlUrl: string): string {
  return socketStlUrl.replace(/socket_shell\.stl$/, "engraving.stl");
}
