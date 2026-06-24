import { useState } from 'react'
import { Link } from 'react-router-dom'
import { preferredTeamLabel } from '../../utils/preferredTeam'

export function followDigestReturnTeam(team, onFollowTeam) {
  if (!team) return false
  onFollowTeam?.(team)
  return true
}

export function DigestReturnNoticeView({
  team,
  relationship = {},
  onFollowTeam = () => {},
  dismissed = false,
  onDismiss = () => {},
}) {
  if (!team || dismissed) return null

  const teamLabel = preferredTeamLabel(team, 'this team')
  const showSwitchPrompt = relationship.showSwitchPrompt === true
  const showSignInPrompt = relationship.showSignInPrompt === true
  const alreadyFollowing = relationship.isFollowing === true

  return (
    <section className="mb-4" aria-label="Digest return">
      <div className="border border-amber/25 bg-amber/10 p-4 sm:p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <div className="font-mono text-[10px] uppercase tracking-widest text-amber">
              Digest Update
            </div>
            <p className="mt-2 text-sm leading-relaxed text-chalk200">
              You're viewing the {teamLabel} update from your digest.
            </p>
            <p className="mt-1 text-sm leading-relaxed text-chalk400">
              Here's what changed for the {teamLabel} since their last game.
            </p>
            {alreadyFollowing && (
              <p className="mt-2 font-mono text-[11px] uppercase tracking-wider text-emerald-300">
                This is already your followed team.
              </p>
            )}
          </div>

          <button
            type="button"
            onClick={onDismiss}
            className="self-start rounded border border-dirt/80 px-2 py-1 font-mono text-[9px] uppercase tracking-widest text-chalk500 transition-colors hover:border-chalk500 hover:text-chalk200"
          >
            Dismiss
          </button>
        </div>

        {(showSwitchPrompt || showSignInPrompt) && (
          <div className="mt-4 flex flex-col gap-3 border-t border-amber/20 pt-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm leading-relaxed text-chalk400">
              {showSwitchPrompt
                ? `Want to make the ${teamLabel} your followed team?`
                : `Sign in to follow this team and get future bullpen updates.`}
            </p>
            {showSwitchPrompt ? (
              <button
                type="button"
                onClick={() => followDigestReturnTeam(team, onFollowTeam)}
                className="inline-flex justify-center rounded border border-amber/35 bg-amber/10 px-3 py-2 font-mono text-[10px] uppercase tracking-widest text-amber transition-colors hover:border-amber/70 hover:bg-amber/15"
              >
                Switch followed team
              </button>
            ) : (
              <Link
                to="/signin"
                className="inline-flex justify-center rounded border border-amber/35 bg-amber/10 px-3 py-2 font-mono text-[10px] uppercase tracking-widest text-amber transition-colors hover:border-amber/70 hover:bg-amber/15"
              >
                Sign in
              </Link>
            )}
          </div>
        )}
      </div>
    </section>
  )
}

export default function DigestReturnNotice(props) {
  const [dismissed, setDismissed] = useState(false)
  return (
    <DigestReturnNoticeView
      {...props}
      dismissed={dismissed}
      onDismiss={() => setDismissed(true)}
    />
  )
}
