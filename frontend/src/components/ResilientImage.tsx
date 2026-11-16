import { useState } from 'react';
import { Film } from 'lucide-react';

interface ResilientImageProps {
  src: string;
  alt: string;
  className?: string;
  fallbackLabel?: string;
}

export function ResilientImage({
  src,
  alt,
  className = '',
  fallbackLabel = '战术映像切片',
}: ResilientImageProps) {
  const [hasError, setHasError] = useState(false);

  if (hasError || !src) {
    return (
      <div
        className={`flex flex-col items-center justify-center bg-gradient-to-br from-slate-100 via-sky-50 to-cyan-50 text-slate-500 ${className}`}
        role="img"
        aria-label={alt}
      >
        <Film className="w-6 h-6 text-[#008DB3] mb-1.5" strokeWidth={1.6} />
        <span className="text-xs font-medium tracking-tight text-slate-600 px-3 text-center">
          {fallbackLabel}
        </span>
      </div>
    );
  }

  return (
    <img
      src={src}
      alt={alt}
      referrerPolicy="no-referrer"
      onError={() => setHasError(true)}
      className={className}
    />
  );
}
