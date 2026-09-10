import { useState } from 'react'
import { requestMagicLink } from '../../utils/api'

export const SIGN_IN_IDLE = 'idle'
export const SIGN_IN_LOADING = 'loading'
export const SIGN_IN_SUCCESS = 'success'
export const SIGN_IN_ERROR = 'error'

export async function submitSignInRequest({
  email,
  requestLink = requestMagicLink,
  setStatus,
  setError,
}) {
  const normalizedEmail = String(email || '').trim()
  if (!normalizedEmail) return false

  setStatus?.(SIGN_IN_LOADING)
  setError?.(null)
  try {
    await requestLink(normalizedEmail)
    setStatus?.(SIGN_IN_SUCCESS)
    return true
  } catch (error) {
    setError?.(error)
    setStatus?.(SIGN_IN_ERROR)
    return false
  }
}

export function SignInView({
  email,
  onEmailChange,
  onSubmit,
  status = SIGN_IN_IDLE,
  error = null,
}) {
  const loading = status === SIGN_IN_LOADING
  const success = status === SIGN_IN_SUCCESS
  const hasError = status === SIGN_IN_ERROR || Boolean(error)

  return (
    <section className="min-h-screen px-4 py-10 sm:px-6 lg:px-10">
      <div className="mx-auto flex min-h-[70vh] w-full max-w-xl items-center">
        <div className="w-full rounded-lg border border-dirt bg-dugout p-6 shadow-2xl shadow-black/20 sm:p-8">
          <div className="font-mono text-[10px] uppercase tracking-widest text-amber/80">
            Sign in
          </div>
          <h1 className="mt-3 font-display text-3xl uppercase tracking-wider text-chalk100">
            BaseballOS
          </h1>
          <p className="mt-3 text-sm leading-relaxed text-chalk400">
            Enter your email and we&apos;ll send a sign-in link.
          </p>

          <form className="mt-6 space-y-4" onSubmit={onSubmit}>
            <label className="block">
              <span className="font-mono text-[10px] uppercase tracking-widest text-chalk500">
                Email
              </span>
              <input
                type="email"
                name="email"
                autoComplete="email"
                value={email}
                onChange={onEmailChange}
                disabled={loading || success}
                required
                className="mt-2 w-full rounded-lg border border-dirt bg-field px-3 py-2.5 text-sm text-chalk100 placeholder:text-chalk600 disabled:cursor-not-allowed disabled:opacity-60"
                placeholder="you@example.com"
              />
            </label>

            <button
              type="submit"
              disabled={loading || success}
              className="w-full rounded-lg border border-amber/40 bg-amber/10 px-4 py-2.5 font-mono text-xs uppercase tracking-widest text-amber transition-colors hover:border-amber/70 hover:bg-amber/15 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? 'Sending...' : 'Send sign-in link'}
            </button>
          </form>

          {success && (
            <p className="mt-5 rounded-lg border border-pine/40 bg-pine/10 px-3 py-2.5 text-sm text-emerald-300">
              Check your email for a sign-in link.
            </p>
          )}

          {hasError && (
            <p className="mt-5 rounded-lg border border-red-500/30 bg-red-500/5 px-3 py-2.5 text-sm text-red-300" role="alert">
              We could not send a sign-in link. Please try again.
            </p>
          )}
        </div>
      </div>
    </section>
  )
}

export default function SignIn() {
  const [email, setEmail] = useState('')
  const [status, setStatus] = useState(SIGN_IN_IDLE)
  const [error, setError] = useState(null)

  const handleSubmit = async (event) => {
    event.preventDefault()
    await submitSignInRequest({
      email,
      setStatus,
      setError,
    })
  }

  return (
    <SignInView
      email={email}
      onEmailChange={(event) => setEmail(event.target.value)}
      onSubmit={handleSubmit}
      status={status}
      error={error}
    />
  )
}
