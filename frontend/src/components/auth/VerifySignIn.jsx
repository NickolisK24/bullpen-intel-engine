import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { verifyMagicLink } from '../../utils/api'

export const VERIFY_LOADING = 'loading'
export const VERIFY_SUCCESS = 'success'
export const VERIFY_FAILURE = 'failure'

export function safeVerifyRedirect(next, fallback = '/') {
  const value = String(next || '').trim()
  if (!value) return fallback
  if (!value.startsWith('/') || value.startsWith('//') || value.startsWith('/\\')) {
    return fallback
  }
  return value
}

export async function verifySignInToken({
  token,
  verifyLink = verifyMagicLink,
  setStatus,
  setError,
}) {
  const normalizedToken = String(token || '').trim()
  if (!normalizedToken) {
    setStatus?.(VERIFY_FAILURE)
    setError?.(new Error('missing_token'))
    return false
  }

  setStatus?.(VERIFY_LOADING)
  setError?.(null)
  try {
    await verifyLink(normalizedToken)
    setStatus?.(VERIFY_SUCCESS)
    return true
  } catch (error) {
    setError?.(error)
    setStatus?.(VERIFY_FAILURE)
    return false
  }
}

export function VerifySignInView({ status = VERIFY_LOADING }) {
  const failure = status === VERIFY_FAILURE

  return (
    <section className="min-h-screen px-4 py-10 sm:px-6 lg:px-10">
      <div className="mx-auto flex min-h-[70vh] w-full max-w-xl items-center">
        <div
          className="w-full rounded-lg border border-dirt bg-dugout p-6 text-center shadow-2xl shadow-black/20 sm:p-8"
          role={failure ? 'alert' : 'status'}
          aria-live="polite"
        >
          <div className="font-mono text-[10px] uppercase tracking-widest text-amber/80">
            Sign in
          </div>

          {status === VERIFY_LOADING && (
            <>
              <h1 className="mt-3 font-display text-3xl uppercase tracking-wider text-chalk100">
                Verifying
              </h1>
              <p className="mt-4 text-sm text-chalk400">
                Verifying sign-in link...
              </p>
            </>
          )}

          {status === VERIFY_SUCCESS && (
            <>
              <h1 className="mt-3 font-display text-3xl uppercase tracking-wider text-chalk100">
                Signed in
              </h1>
              <p className="mt-4 text-sm text-chalk400">
                Taking you back to BaseballOS.
              </p>
            </>
          )}

          {failure && (
            <>
              <h1 className="mt-3 font-display text-3xl uppercase tracking-wider text-chalk100">
                Link expired
              </h1>
              <p className="mt-4 text-sm text-chalk400">
                This sign-in link is invalid or expired.
              </p>
              <Link
                to="/signin"
                className="mt-6 inline-flex rounded-lg border border-amber/40 bg-amber/10 px-4 py-2.5 font-mono text-xs uppercase tracking-widest text-amber transition-colors hover:border-amber/70 hover:bg-amber/15"
              >
                Request a new link
              </Link>
            </>
          )}
        </div>
      </div>
    </section>
  )
}

export default function VerifySignIn() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [status, setStatus] = useState(VERIFY_LOADING)
  const [error, setError] = useState(null)
  const token = searchParams.get('token')
  const next = safeVerifyRedirect(searchParams.get('next'))

  useEffect(() => {
    let active = true

    verifySignInToken({
      token,
      setStatus: (nextStatus) => {
        if (active) setStatus(nextStatus)
      },
      setError: (nextError) => {
        if (active) setError(nextError)
      },
    })
      .then((verified) => {
        if (!active || !verified) return
        window.setTimeout(() => {
          if (active) navigate(next, { replace: true })
        }, 600)
      })

    return () => {
      active = false
    }
  }, [navigate, next, token])

  return <VerifySignInView status={error ? VERIFY_FAILURE : status} />
}
