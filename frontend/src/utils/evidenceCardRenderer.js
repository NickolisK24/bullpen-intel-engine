import { measureCardText, wrapCardText } from './evidenceCardText'
import {
  COMPARISON_HEADLINE_LAYOUT,
  COMPARISON_SUPPORTING_LAYOUT,
  TEAM_HEADLINE_LAYOUT,
  TEAM_SUPPORTING_LAYOUT,
} from './evidenceCardStory'

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

function textBlock(lines, { x, y, size, lineHeight, fill = '#F3F0E8', weight = 500 }) {
  return lines.map((line, index) => (
    `<text x="${x}" y="${y + index * lineHeight}" fill="${fill}" font-family="Arial, Helvetica, sans-serif" font-size="${size}" font-weight="${weight}">${escapeSvgText(line)}</text>`
  )).join('')
}

function shell(content) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${EVIDENCE_CARD_WIDTH}" height="${EVIDENCE_CARD_HEIGHT}" viewBox="0 0 ${EVIDENCE_CARD_WIDTH} ${EVIDENCE_CARD_HEIGHT}" role="img"><rect width="1200" height="630" fill="#0D1712"/><rect x="24" y="24" width="1152" height="582" rx="12" fill="#14231B" stroke="#38503F" stroke-width="2"/><rect x="48" y="48" width="8" height="54" fill="#F5A623"/>${content}</svg>`
}

function footer(model) {
  const cta = model.evidenceCtaLabel
    ? textBlock([model.evidenceCtaLabel], { x: 1144, y: 565, size: 14, lineHeight: 18, fill: '#8FA298', weight: 700 }).replace('x="1144"', 'x="1144" text-anchor="end"')
    : ''
  return `<line x1="56" y1="536" x2="1144" y2="536" stroke="#38503F"/>${textBlock([
    model.limitation,
  ], { x: 56, y: 565, size: 18, lineHeight: 22, fill: '#B7C1B9' })}${cta}${textBlock([
    model.displayUrl,
  ], { x: 1144, y: 592, size: 15, lineHeight: 19, fill: '#F5A623', weight: 700 }).replace('x="1144"', 'x="1144" text-anchor="end"')}`
}

function stateBadge(stateLabel, x, y) {
  const label = `BASEBALLOS STATE · ${stateLabel.toUpperCase()}`
  const width = Math.ceil(measureCardText(label, 14)) + 32
  return `<rect x="${x}" y="${y}" width="${width}" height="32" rx="6" fill="#0D1712" stroke="#38503F"/>${textBlock([label], {
    x: x + 16, y: y + 21, size: 14, lineHeight: 18, fill: '#F5A623', weight: 700,
  })}`
}

function teamSvg(model) {
  const teamNameLines = wrapCardText(`${model.teamName.toUpperCase()} BULLPEN`, {
    maxWidth: 548, maxLines: 2, fontSize: 20,
  })
  const headlineLines = wrapCardText(model.headline, TEAM_HEADLINE_LAYOUT)
  const supportingLines = model.supportingLine
    ? wrapCardText(model.supportingLine, TEAM_SUPPORTING_LAYOUT)
    : []
  const supportingBlock = supportingLines?.length
    ? textBlock(supportingLines, { x: 56, y: 372, size: 20, lineHeight: 26 })
    : ''
  const receipts = model.receipts.slice(0, 3).map(receipt => wrapCardText(receipt, {
    maxWidth: 404, maxLines: 2, fontSize: 18,
  })).filter(Boolean)
  const receiptBlocks = receipts.map((lines, index) => textBlock(
    lines.map((line, lineIndex) => `${lineIndex === 0 ? '• ' : '  '}${line}`),
    { x: 700, y: 220 + index * 72, size: 18, lineHeight: 25, fill: '#D8DDD8' },
  )).join('')
  return shell(`
    ${textBlock(['BASEBALLOS', 'BULLPEN INTELLIGENCE'], { x: 72, y: 70, size: 20, lineHeight: 26, fill: '#F5A623', weight: 700 })}
    ${textBlock(teamNameLines, { x: 56, y: 140, size: 20, lineHeight: 25, fill: '#D8DDD8', weight: 700 })}
    ${textBlock(headlineLines, { x: 56, y: 210, size: 34, lineHeight: 40, fill: '#F5A623', weight: 800 })}
    ${supportingBlock}
    <rect x="668" y="132" width="476" height="342" rx="8" fill="#0D1712" stroke="#38503F"/>
    ${textBlock(['RECEIPTS'], { x: 700, y: 174, size: 16, lineHeight: 20, fill: '#8FA298', weight: 700 })}
    ${receiptBlocks}
    ${stateBadge(model.stateLabel, 56, 428)}
    ${textBlock([`Data through ${model.dataThroughLabel}`], { x: 56, y: 510, size: 18, lineHeight: 22, fill: '#D8DDD8', weight: 700 })}
    ${footer(model)}
  `)
}

function comparisonSvg(model) {
  const startY = 344
  const rows = model.rows.map((row, index) => {
    const y = startY + index * 42
    return `<line x1="56" y1="${y + 14}" x2="720" y2="${y + 14}" stroke="#38503F"/>${textBlock([row.label.toUpperCase()], { x: 56, y, size: 18, lineHeight: 22, fill: '#B7C1B9', weight: 700 })}${textBlock([String(row.valueA)], { x: 360, y, size: 24, lineHeight: 26, weight: 700 }).replace('x="360"', 'x="360" text-anchor="middle"')}${textBlock([String(row.valueB)], { x: 640, y, size: 24, lineHeight: 26, weight: 700 }).replace('x="640"', 'x="640" text-anchor="middle"')}`
  }).join('')
  const freshness = model.freshnessA === model.freshnessB
    ? `Data through ${model.freshnessALabel}`
    : `${model.teamA.abbreviation}: ${model.freshnessALabel}  •  ${model.teamB.abbreviation}: ${model.freshnessBLabel}`
  const headlineLines = wrapCardText(model.headline, COMPARISON_HEADLINE_LAYOUT)
  const teamALines = wrapCardText(model.teamA.name.toUpperCase(), {
    maxWidth: 220, maxLines: 2, fontSize: 22,
  })
  const teamBLines = wrapCardText(model.teamB.name.toUpperCase(), {
    maxWidth: 220, maxLines: 2, fontSize: 22,
  })
  const supportingLines = model.supportingLine
    ? wrapCardText(model.supportingLine, COMPARISON_SUPPORTING_LAYOUT)
    : []
  const supportingBlock = supportingLines?.length
    ? `<rect x="760" y="232" width="384" height="250" rx="8" fill="#0D1712" stroke="#38503F"/>${textBlock(['ALSO IN THIS READ'], { x: 788, y: 268, size: 16, lineHeight: 20, fill: '#8FA298', weight: 700 })}${textBlock(supportingLines, { x: 788, y: 302, size: 20, lineHeight: 28 })}`
    : ''
  return shell(`
    ${textBlock(['BASEBALLOS', 'CURRENT BULLPEN COMPARISON'], { x: 72, y: 70, size: 20, lineHeight: 26, fill: '#F5A623', weight: 700 })}
    ${textBlock(headlineLines, { x: 56, y: 150, size: 30, lineHeight: 38, fill: '#F5A623', weight: 800 })}
    ${textBlock(teamALines, { x: 360, y: 240, size: 22, lineHeight: 25, weight: 700 }).replaceAll('x="360"', 'x="360" text-anchor="middle"')}
    ${textBlock(['VS'], { x: 500, y: 252, size: 16, lineHeight: 20, fill: '#8FA298', weight: 700 }).replace('x="500"', 'x="500" text-anchor="middle"')}
    ${textBlock(teamBLines, { x: 640, y: 240, size: 22, lineHeight: 25, weight: 700 }).replaceAll('x="640"', 'x="640" text-anchor="middle"')}
    ${textBlock([model.teamA.abbreviation], { x: 360, y: 306, size: 16, lineHeight: 20, fill: '#F5A623', weight: 700 }).replace('x="360"', 'x="360" text-anchor="middle"')}
    ${textBlock([model.teamB.abbreviation], { x: 640, y: 306, size: 16, lineHeight: 20, fill: '#F5A623', weight: 700 }).replace('x="640"', 'x="640" text-anchor="middle"')}
    ${rows}
    ${supportingBlock}
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
