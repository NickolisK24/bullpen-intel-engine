import { useEffect } from 'react'
import {
  recordStoryViewed,
  recordTodayLoaded,
} from '../utils/api'
import {
  observeStoryViewedOnce,
  observeTodayLoadedOnce,
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
