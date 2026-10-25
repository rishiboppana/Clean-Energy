// FE5: absorbable = min(grid surplus, hub headroom), shown as a share of headroom (0..1).
export function absorbable(surplusMw: number, headroomMw: number) {
  const mw = Math.max(0, Math.min(surplusMw, headroomMw))
  return { mw, share: mw / headroomMw }
}
