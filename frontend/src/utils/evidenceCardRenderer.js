export const EVIDENCE_CARD_WIDTH = 1200
export const EVIDENCE_CARD_HEIGHT = 630

export function escapeSvgText(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&apos;')
}

function bounded(value, limit) {
  const text = String(value || '').trim().replace(/\s+/g, ' ')
  return text.length <= limit ? text : `${text.slice(0, limit - 1).trimEnd()}…`
}

function wrap(value, maxChars, maxLines) {
  const words = bounded(value, maxChars * maxLines).split(' ').filter(Boolean)
  const lines = []
  for (const word of words) {
    const current = lines.at(-1)
    if (!current || `${current} ${word}`.length > maxChars) {
      if (lines.length === maxLines) break
      lines.push(word)
    } else {
      lines[lines.length - 1] = `${current} ${word}`
    }
  }
  if (words.length && lines.join(' ').length < words.join(' ').length) {
    lines[lines.length - 1] = bounded(lines.at(-1), Math.max(2, maxChars - 1)).replace(/…?$/, '…')
  }
  return lines
}

function textBlock(lines, { x, y, size, lineHeight, fill = '#F3F0E8', weight = 500 }) {
  return lines.map((line, index) => (
    `<text x="${x}" y="${y + index * lineHeight}" fill="${fill}" font-family="Arial, Helvetica, sans-serif" font-size="${size}" font-weight="${weight}">${escapeSvgText(line)}</text>`
  )).join('')
}

function shell(content) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${EVIDENCE_CARD_WIDTH}" height="${EVIDENCE_CARD_HEIGHT}" viewBox="0 0 ${EVIDENCE_CARD_WIDTH} ${EVIDENCE_CARD_HEIGHT}" role="img"><rect width="1200" height="630" fill="#0D1712"/><rect x="24" y="24" width="1152" height="582" rx="12" fill="#14231B" stroke="#38503F" stroke-width="2"/><rect x="48" y="48" width="8" height="54" fill="#F5A623"/>${content}</svg>`
}

function footer(model) {
  const destination = bounded(model.destinationUrl.replace(/^https?:\/\//, ''), 82)
  return `<line x1="56" y1="536" x2="1144" y2="536" stroke="#38503F"/>${textBlock([
    model.limitation,
  ], { x: 56, y: 565, size: 18, lineHeight: 22, fill: '#B7C1B9' })}${textBlock([
    destination,
  ], { x: 1144, y: 592, size: 18, lineHeight: 22, fill: '#F5A623', weight: 700 }).replace('x="1144"', 'x="1144" text-anchor="end"')}`
}

function teamSvg(model) {
  const receiptLines = model.receipts.flatMap(receipt => wrap(`• ${receipt}`, 74, 2))
  return shell(`
    ${textBlock(['BASEBALLOS', 'BULLPEN INTELLIGENCE'], { x: 72, y: 70, size: 20, lineHeight: 26, fill: '#F5A623', weight: 700 })}
    ${textBlock([`${model.teamName.toUpperCase()} BULLPEN`], { x: 56, y: 150, size: 34, lineHeight: 40, weight: 700 })}
    ${textBlock([model.stateLabel.toUpperCase()], { x: 56, y: 207, size: 46, lineHeight: 50, fill: '#F5A623', weight: 800 })}
    ${textBlock(wrap(model.summary, 68, 2), { x: 56, y: 246, size: 24, lineHeight: 30 })}
    ${textBlock(['WHY'], { x: 56, y: 326, size: 16, lineHeight: 20, fill: '#8FA298', weight: 700 })}
    ${textBlock(wrap(model.why, 70, 2), { x: 56, y: 358, size: 21, lineHeight: 27 })}
    ${textBlock(['RECEIPTS'], { x: 646, y: 207, size: 16, lineHeight: 20, fill: '#8FA298', weight: 700 })}
    ${textBlock(receiptLines.slice(0, 6), { x: 646, y: 242, size: 18, lineHeight: 27, fill: '#D8DDD8' })}
    ${textBlock([`Data through ${model.dataThroughLabel}`], { x: 56, y: 510, size: 18, lineHeight: 22, fill: '#D8DDD8', weight: 700 })}
    ${footer(model)}
  `)
}

function comparisonSvg(model) {
  const startY = 270
  const rows = model.rows.map((row, index) => {
    const y = startY + index * 48
    return `<line x1="56" y1="${y + 14}" x2="720" y2="${y + 14}" stroke="#38503F"/>${textBlock([row.label.toUpperCase()], { x: 56, y, size: 18, lineHeight: 22, fill: '#B7C1B9', weight: 700 })}${textBlock([String(row.valueA)], { x: 516, y, size: 24, lineHeight: 26, weight: 700 }).replace('x="516"', 'x="516" text-anchor="end"')}${textBlock([String(row.valueB)], { x: 704, y, size: 24, lineHeight: 26, weight: 700 }).replace('x="704"', 'x="704" text-anchor="end"')}`
  }).join('')
  const freshness = model.freshnessA === model.freshnessB
    ? `Data through ${model.freshnessALabel}`
    : `${model.teamA.abbreviation}: ${model.freshnessALabel}  •  ${model.teamB.abbreviation}: ${model.freshnessBLabel}`
  return shell(`
    ${textBlock(['BASEBALLOS', 'CURRENT BULLPEN COMPARISON'], { x: 72, y: 70, size: 20, lineHeight: 26, fill: '#F5A623', weight: 700 })}
    ${textBlock([model.teamA.name.toUpperCase()], { x: 56, y: 164, size: 30, lineHeight: 34, weight: 700 })}
    ${textBlock([model.teamB.name.toUpperCase()], { x: 704, y: 164, size: 30, lineHeight: 34, weight: 700 }).replace('x="704"', 'x="704" text-anchor="end"')}
    ${textBlock([model.teamA.abbreviation], { x: 516, y: 218, size: 16, lineHeight: 20, fill: '#F5A623', weight: 700 }).replace('x="516"', 'x="516" text-anchor="end"')}
    ${textBlock([model.teamB.abbreviation], { x: 704, y: 218, size: 16, lineHeight: 20, fill: '#F5A623', weight: 700 }).replace('x="704"', 'x="704" text-anchor="end"')}
    ${rows}
    <rect x="760" y="190" width="384" height="256" rx="8" fill="#0D1712" stroke="#38503F"/>
    ${textBlock(['WHAT DIFFERS'], { x: 788, y: 226, size: 16, lineHeight: 20, fill: '#8FA298', weight: 700 })}
    ${textBlock(wrap(model.observation, 34, 5), { x: 788, y: 266, size: 22, lineHeight: 31 })}
    ${textBlock([freshness], { x: 56, y: 510, size: 18, lineHeight: 22, fill: '#D8DDD8', weight: 700 })}
    ${footer(model)}
  `)
}

export function renderEvidenceCardSvg(model) {
  if (model?.cardType === 'team') return teamSvg(model)
  if (model?.cardType === 'comparison') return comparisonSvg(model)
  throw new Error('unsupported_card_model')
}

export async function renderEvidenceCardPng(model, env = globalThis) {
  const svg = renderEvidenceCardSvg(model)
  const BlobCtor = env.Blob
  const ImageCtor = env.Image
  const documentRef = env.document
  const urlApi = env.URL
  if (!BlobCtor || !ImageCtor || !documentRef?.createElement || !urlApi?.createObjectURL) {
    throw new Error('card_rendering_unavailable')
  }
  const svgUrl = urlApi.createObjectURL(new BlobCtor([svg], { type: 'image/svg+xml;charset=utf-8' }))
  try {
    const image = await new Promise((resolve, reject) => {
      const value = new ImageCtor()
      value.onload = () => resolve(value)
      value.onerror = () => reject(new Error('card_image_load_failed'))
      value.src = svgUrl
    })
    const canvas = documentRef.createElement('canvas')
    canvas.width = EVIDENCE_CARD_WIDTH
    canvas.height = EVIDENCE_CARD_HEIGHT
    const context = canvas.getContext?.('2d')
    if (!context || typeof canvas.toBlob !== 'function') throw new Error('card_canvas_unavailable')
    context.drawImage(image, 0, 0, EVIDENCE_CARD_WIDTH, EVIDENCE_CARD_HEIGHT)
    return await new Promise((resolve, reject) => {
      canvas.toBlob(
        blob => (blob ? resolve(blob) : reject(new Error('card_png_failed'))),
        'image/png',
      )
    })
  } finally {
    urlApi.revokeObjectURL(svgUrl)
  }
}
