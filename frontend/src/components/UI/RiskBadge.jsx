import { riskBadgeClass } from '../../utils/formatters'

export default function RiskBadge({ level }) {
  const cls = riskBadgeClass(level)
  const dots = { LOW: 1, MODERATE: 2, HIGH: 3, CRITICAL: 4 }[level] || 1
  return (
    <span className={cls}>
      {'●'.repeat(dots)}{'○'.repeat(4 - dots)} {level}
    </span>
  )
}
