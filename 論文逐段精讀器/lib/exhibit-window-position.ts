export type WindowOffset = { x: number; y: number };

/** Keep a center-positioned floating window entirely within the viewport. */
export function clampWindowOffset(
  offset: WindowOffset,
  size: { width: number; height: number },
  viewport: { width: number; height: number },
  gutter = 16,
): WindowOffset {
  const limitX = Math.max(0, (viewport.width - size.width) / 2 - gutter);
  const limitY = Math.max(0, (viewport.height - size.height) / 2 - gutter);
  return {
    x: limitX === 0 ? 0 : Math.max(-limitX, Math.min(limitX, Number.isFinite(offset.x) ? offset.x : 0)),
    y: limitY === 0 ? 0 : Math.max(-limitY, Math.min(limitY, Number.isFinite(offset.y) ? offset.y : 0)),
  };
}
