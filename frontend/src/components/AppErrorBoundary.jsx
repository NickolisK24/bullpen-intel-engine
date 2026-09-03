import React, { useEffect, useRef } from 'react'
import { captureFrontendError } from '../utils/errorMonitoring'

export function AppErrorFallback({ onReload = null }) {
  const errorRef = useRef(null)
  const reload = onReload || (() => {
    if (typeof window !== 'undefined' && window.location?.reload) {
      window.location.reload()
    }
  })

  useEffect(() => {
    errorRef.current?.focus()
  }, [])

  return (
    <main
      ref={errorRef}
      tabIndex={-1}
      role="alert"
      aria-labelledby="app-error-title"
      aria-describedby="app-error-description"
      className="min-h-screen bg-dugout px-6 py-12 text-chalk100 outline-none"
    >
      <div className="mx-auto flex min-h-[70vh] w-full max-w-2xl flex-col justify-center">
        <div className="border border-chalk700 bg-field p-6 sm:p-8">
          <p className="font-mono text-xs uppercase tracking-[0.24em] text-metadata-accent">
            BaseballOS
          </p>
          <h1 id="app-error-title" className="mt-4 text-2xl font-semibold text-chalk100 sm:text-3xl">
            Something went wrong while loading this BaseballOS view.
          </h1>
          <p id="app-error-description" className="mt-3 max-w-xl text-sm leading-6 text-chalk300">
            Try refreshing the page.
          </p>
          <button
            type="button"
            onClick={reload}
            className="mt-6 inline-flex min-h-11 w-fit items-center border border-chalk300 bg-chalk100 px-4 py-2 font-mono text-xs uppercase tracking-[0.18em] text-field transition hover:bg-chalk200 focus-visible:ring-2 focus-visible:ring-line-focus"
          >
            Reload
          </button>
        </div>
      </div>
    </main>
  )
}

export default class AppErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error, errorInfo) {
    const capture = this.props.captureError || captureFrontendError
    capture(error, {
      source: 'react_error_boundary',
      component_stack: errorInfo?.componentStack,
    })
  }

  render() {
    if (this.state.hasError) {
      return <AppErrorFallback onReload={this.props.onReload} />
    }

    return this.props.children
  }
}
