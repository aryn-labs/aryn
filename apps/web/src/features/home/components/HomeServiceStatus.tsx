import { AlertCircle, ChevronDown } from 'lucide-react'
import { ApiError } from '@/lib/api/client'
export function HomeServiceStatus({
  services,
}: {
  services: { label: string; error: Error; retry: () => void }[]
}) {
  if (!services.length) return null
  return (
    <details className="home-service-status" aria-label="Overview availability">
      <summary>
        <AlertCircle size={17} aria-hidden="true" />
        <span>Some workspace data is unavailable</span>
        <span className="home-service-count">
          {services.length} {services.length === 1 ? 'service' : 'services'}
        </span>
        <ChevronDown size={16} aria-hidden="true" />
      </summary>
      <div className="home-service-details">
        <p>
          Available work is shown below. Expand each service’s availability here; missing data does
          not mean an empty project.
        </p>
        <ul>
          {services.map((service) => (
            <li key={service.label}>
              <span>
                {service.label}:{' '}
                {service.error instanceof ApiError && [404, 501].includes(service.error.status)
                  ? 'unavailable on this server'
                  : 'unable to load data'}
              </span>
              <button onClick={service.retry}>
                Try again<span className="sr-only"> — {service.label}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </details>
  )
}
