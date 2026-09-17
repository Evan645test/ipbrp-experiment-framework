import type { ImgHTMLAttributes } from "react";

type StaticImageProps = ImgHTMLAttributes<HTMLImageElement> & { unoptimized?: boolean };

/** Static hosting has no image optimizer; the original cropped image is used. */
export default function StaticImage({ unoptimized, alt, ...props }: StaticImageProps) {
  void unoptimized;
  // eslint-disable-next-line @next/next/no-img-element
  return <img {...props} alt={alt ?? ""} />;
}
