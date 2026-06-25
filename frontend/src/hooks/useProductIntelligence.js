import { useEffect, useRef } from 'react'
import {
  recordStoryImpression,
  recordStoryViewed,
  recordTodayLoaded,
} from '../utils/api'
import {
  createStoryImpressionTracker,
  observeStoryViewedOnce,
  observeTodayLoadedOnce,
  storyImpressionRefKey,
} from '../utils/productIntelligence'

export function useTodayLoadedObservation({
  loaded = false,
  teamId = null,
  source = 'direct',
} = {}) {
  useEffect(() => {
    observeTodayLoadedOnce({
      loaded,
      teamId,
      source,
      send: recordTodayLoaded,
    })
  }, [loaded, source, teamId])
}

// Retired from the render path in V3-1: the in-product surfaces no longer call
// this on render (a render is not a view). It is kept for the still-live
// /story-viewed endpoint and as the home for a future meaningful-consumption
// trigger. New on-screen tracking lives in useStoryImpressionObservations below.
export function useStoryViewedObservations({
  enabled = true,
  stories = [],
  surface = null,
} = {}) {
  const storyKey = (Array.isArray(stories) ? stories : [])
    .map(story => [
      story?.storyId || story?.story_id || '',
      story?.storyType || story?.story_type || '',
      story?.teamId || story?.team_id || '',
    ].join(':'))
    .join('|')

  useEffect(() => {
    if (!enabled) return
    observeStoryViewedOnce({
      stories,
      surface,
      send: recordStoryViewed,
    })
  }, [enabled, storyKey, surface])
}

// V3-1: viewport-based story impressions. A story card emits story_impression
// only when it actually appears on screen (IntersectionObserver ≈ 50%+ visible),
// replacing the render-fired story_viewed beacon. Returns a ref-factory: call it
// with a story to get a stable ref callback, and attach that to the card element
// (`ref={register(story)}`). Fires once per story per surface per browser session;
// no-ops where IntersectionObserver is unavailable; disconnects observers on
// unmount. Cards without a canonical story identity yield no ref (never observed).
export function useStoryImpressionObservations({
  enabled = true,
  surface = null,
} = {}) {
  const trackerRef = useRef(null)
  const elementByKey = useRef(new Map())
  const storyByKey = useRef(new Map())
  const refCallbacks = useRef(new Map())

  useEffect(() => {
    if (!enabled) return undefined
    const tracker = createStoryImpressionTracker({ surface, send: recordStoryImpression })
    trackerRef.current = tracker
    // Observe any cards whose refs attached before the tracker existed.
    for (const [key, element] of elementByKey.current) {
      const story = storyByKey.current.get(key)
      if (element && story) tracker.observe(element, story)
    }
    return () => {
      tracker.disconnect()
      trackerRef.current = null
    }
  }, [enabled, surface])

  return (story) => {
    const key = storyImpressionRefKey(story)
    if (!key) return undefined // cards without a canonical story identity
    const cached = refCallbacks.current.get(key)
    if (cached) return cached
    const callback = (element) => {
      const tracker = trackerRef.current
      if (element) {
        elementByKey.current.set(key, element)
        storyByKey.current.set(key, story)
        if (tracker) tracker.observe(element, story)
      } else {
        const previous = elementByKey.current.get(key)
        elementByKey.current.delete(key)
        storyByKey.current.delete(key)
        if (tracker && previous) tracker.unobserve(previous)
      }
    }
    refCallbacks.current.set(key, callback)
    return callback
  }
}
