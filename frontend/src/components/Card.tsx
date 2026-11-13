import type { ReactNode } from 'react'
import type { Status } from '../api'
import Badge from './Badge'
interface CardProps {
  title: string
  status: Status
  children: ReactNode
}
export default function Card({ title, status, children }: CardProps) {
  return (
    <article className="metric">
      <div className="card-heading">
        <h3>{title}</h3>
        <Badge status={status} />
      </div>
      {children}
    </article>
  )
}
