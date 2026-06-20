import { useState } from 'react'
import {
  preferredTeamLogoUrl,
  preferredTeamShortLabel,
} from '../../utils/preferredTeam'

export default function TeamMark({
  team,
  className = '',
  imageClassName = '',
  fallbackClassName = '',
}) {
  const [failed, setFailed] = useState(false)
  const logoUrl = failed ? null : preferredTeamLogoUrl(team)
  const fallback = preferredTeamShortLabel(team).slice(0, 3)

  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center overflow-hidden rounded border border-white/10 bg-white/[0.03] ${className}`}
      aria-hidden="true"
    >
      {logoUrl ? (
        <img
          src={logoUrl}
          alt=""
          loading="lazy"
          decoding="async"
          className={`h-full w-full object-contain ${imageClassName}`}
          onError={() => setFailed(true)}
        />
      ) : (
        <span className={`font-display tracking-wide text-amber ${fallbackClassName}`}>
          {fallback}
        </span>
      )}
    </span>
  )
}
