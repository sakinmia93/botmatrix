import React, { useEffect, useState } from 'react';
import { Bot as BotGlyph } from 'lucide-react';

/** Bot profile photo. When there is no photo (or it fails to load) the bot icon is shown instead — never a broken image. */
export const BotAvatar: React.FC<{ src?: string | null; alt?: string; className?: string; iconClassName?: string }> = ({ src, alt = '', className = '', iconClassName = 'w-1/2 h-1/2' }) => {
  const [failed, setFailed] = useState(false);
  useEffect(() => { setFailed(false); }, [src]);
  return (
    <div className={`bg-gradient-to-tr from-blue-600 via-indigo-600 to-purple-600 text-white flex items-center justify-center overflow-hidden ${className}`}>
      {src && !failed ? (
        <img src={src} alt={alt} className="w-full h-full object-cover" referrerPolicy="no-referrer" loading="lazy" decoding="async" onError={() => setFailed(true)} />
      ) : (
        <BotGlyph className={`text-white ${iconClassName}`} />
      )}
    </div>
  );
};
