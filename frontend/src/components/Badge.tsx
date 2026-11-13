import type { Status } from '../api'
interface BadgeProps {
  status: Status
}
const names: Record<Status, string> = {
  healthy: 'Healthy',
  warning: 'Review',
  critical: 'Critical',
  unknown: 'Unknown',
}
export default function Badge({ status }: BadgeProps) {
  return <span className={`badge ${status}`}>{names[status]}</span>
}
