import { ImageOff } from "lucide-react";
import { useState } from "react";
import { cx } from "../lib/format";

/**
 * A real photo, or an honest placeholder. Paths are relative to the add-on's
 * photo dir and served at ./photos/ (relative, for HA ingress).
 */
export default function WatchImage({
  photo,
  refId,
  label,
  className,
  compact,
}: {
  photo: string | null | undefined;
  refId: string;
  label?: string;
  className?: string;
  compact?: boolean;
}) {
  const [broken, setBroken] = useState(false);
  if (photo && !broken) {
    return <img src={`photos/${photo}`} alt={label ?? refId} loading="lazy" onError={() => setBroken(true)} className={cx("h-full w-full object-contain", className)} />;
  }
  return (
    <div className={cx("flex h-full w-full flex-col items-center justify-center gap-2 text-center", className)}>
      <ImageOff size={compact ? 14 : 22} strokeWidth={1.4} className="text-faint" />
      {!compact && (
        <>
          <span className="font-mono text-[12px] text-muted">{refId}</span>
          <span className="eyebrow text-faint">Photo needed</span>
        </>
      )}
    </div>
  );
}
