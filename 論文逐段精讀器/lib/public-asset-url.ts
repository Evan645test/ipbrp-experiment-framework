/** Resolve public files on both localhost and a GitHub Pages project path. */
export function publicAssetUrl(path: string): string {
  if (typeof document === "undefined" || !path.startsWith("/") || path.startsWith("//")) return path;
  const base = document.querySelector<HTMLMetaElement>('meta[name="paper-reader-base"]')?.content ?? "/";
  if (base === "/") return path;
  return `${base.replace(/\/$/, "")}${path}`;
}
