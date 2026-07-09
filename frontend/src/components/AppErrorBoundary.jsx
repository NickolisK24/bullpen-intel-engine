import React from 'react'
import { captureFrontendError } from '../utils/errorMonitoring'

export function AppErrorFallback({ onReload = null }) {
  const reload = onReload || (() => {
    if (typeof window !== 'undefined' && window.location?.reload) {
      window.location.reload()
    }
  })

  return (
    <main className="min-h-screen bg-dugout text-chalk px-6 py-12">
      <div className="mx-auto flex min-h-[70vh] w-full max-w-2xl flex-col justify-center">
        <div className="border border-chalk/10 bg-black/20 p-6 sm:p-8">
          <p className="font-mono text-xs uppercase tracking-[0.24em] text-chalk/55">
            BaseballOS
          </p>
          <h1 className="mt-4 text-2xl font-semibold text-chalk sm:text-3xl">
            Something went wrong while loading this BaseballOS view.
          </h1>
          <p className="mt-3 max-w-xl text-sm leading-6 text-chalk/70">
            Try refreshing the page.
          </p>
          <button
            type="button"
            onClick={reload}
            className="mt-6 inline-flex w-fit items-center border border-chalk/20 bg-chalk px-4 py-2 font-mono text-xs uppercase tracking-[0.18em] text-dugout transition hover:bg-chalk/90"
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
