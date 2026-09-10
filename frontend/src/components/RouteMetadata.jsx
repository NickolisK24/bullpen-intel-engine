import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { metadataForLocation } from '../utils/publicRouteMetadata'

function upsertMeta(selector, attributes) {
  let element = document.head.querySelector(selector)
  if (!element) {
    element = document.createElement('meta')
    document.head.appendChild(element)
  }
  for (const [name, value] of Object.entries(attributes)) {
    element.setAttribute(name, value)
  }
  return element
}

function setCanonical(url) {
  const existing = document.head.querySelector('link[rel="canonical"]')
  if (!url) {
    existing?.remove()
    return
  }
  const link = existing || document.createElement('link')
  link.setAttribute('rel', 'canonical')
  link.setAttribute('href', url)
  if (!existing) document.head.appendChild(link)
}

export default function RouteMetadata() {
  const location = useLocation()

  useEffect(() => {
    const metadata = metadataForLocation(location.pathname, location.search)
    if (metadata?.externallyManaged) return
    if (!metadata) {
      document.title = 'Page not found · BaseballOS'
      setCanonical(null)
      upsertMeta('meta[name="robots"]', { name: 'robots', content: 'noindex,nofollow' })
      document.head.querySelector('meta[property="og:url"]')?.remove()
      return
    }

    document.title = metadata.title
    upsertMeta('meta[name="description"]', { name: 'description', content: metadata.description })
    setCanonical(metadata.canonicalUrl)
    upsertMeta('meta[property="og:title"]', { property: 'og:title', content: metadata.title })
    upsertMeta('meta[property="og:description"]', { property: 'og:description', content: metadata.description })
    if (metadata.canonicalUrl) {
      upsertMeta('meta[property="og:url"]', { property: 'og:url', content: metadata.canonicalUrl })
    } else {
      document.head.querySelector('meta[property="og:url"]')?.remove()
    }
    if (metadata.robots) {
      upsertMeta('meta[name="robots"]', { name: 'robots', content: metadata.robots })
    } else {
      document.head.querySelector('meta[name="robots"]')?.remove()
    }
  }, [location.pathname, location.search])

  return null
}
