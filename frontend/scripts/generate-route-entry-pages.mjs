import { mkdir, rm, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { PUBLIC_ORIGIN, ROUTE_ENTRY_METADATA } from '../src/utils/publicRouteMetadata.js'

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url))
export const ROUTE_ENTRY_DIR = resolve(SCRIPT_DIR, '../route-entry')

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('"', '&quot;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
}

export function renderRouteEntryHtml(entry) {
  const canonicalUrl = entry.canonical ? `${PUBLIC_ORIGIN}${entry.canonical}` : null
  const socialUrl = canonicalUrl
  const robots = entry.robots
  return `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>${escapeHtml(entry.title)}</title>
    <meta name="description" content="${escapeHtml(entry.description)}" />
${robots ? `    <meta name="robots" content="${escapeHtml(robots)}" />\n` : ''}${canonicalUrl ? `    <link rel="canonical" href="${escapeHtml(canonicalUrl)}" />\n` : ''}    <meta property="og:site_name" content="BaseballOS" />
    <meta property="og:type" content="website" />
    <meta property="og:title" content="${escapeHtml(entry.title)}" />
    <meta property="og:description" content="${escapeHtml(entry.description)}" />
${socialUrl ? `    <meta property="og:url" content="${escapeHtml(socialUrl)}" />\n` : ''}    <meta property="og:image" content="https://baseballos.app/og/baseballos-card.png" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="${escapeHtml(entry.title)}" />
    <meta name="twitter:description" content="${escapeHtml(entry.description)}" />
    <meta name="twitter:image" content="https://baseballos.app/og/baseballos-card.png" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <link rel="manifest" href="/manifest.webmanifest" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&amp;family=DM+Sans:wght@300;400;500;600&amp;family=Inter:wght@400;500;600&amp;family=JetBrains+Mono:wght@400;500;600&amp;display=swap" rel="stylesheet" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
`
}

export async function writeRouteEntryPages(outputDir = ROUTE_ENTRY_DIR) {
  await rm(outputDir, { recursive: true, force: true })
  await mkdir(outputDir, { recursive: true })
  for (const entry of ROUTE_ENTRY_METADATA) {
    await writeFile(resolve(outputDir, `${entry.key}.html`), renderRouteEntryHtml(entry), 'utf8')
  }
  return ROUTE_ENTRY_METADATA.length
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const count = await writeRouteEntryPages()
  process.stdout.write(`Generated ${count} route entry pages.\n`)
}
