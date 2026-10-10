import { labelText } from '@/i18n'
import { translate as tr } from '@/i18n'
import { useTranslation } from 'react-i18next'
import { AlertCircle, ChevronDown } from 'lucide-react'
import { ApiError } from '@/lib/api/client'
export function HomeServiceStatus({
  services,
}: {
  services: { label: string; error: Error; retry: () => void }[]
}) {
  useTranslation()

  if (!services.length) return null
  return (
    <details className="home-service-status" aria-label={tr('ui.overview_availability')}>
      <summary>
        <AlertCircle size={17} aria-hidden="true" />
        <span>{tr('ui.some_workspace_data_is_unavailable')}</span>
        <span className="home-service-count">{services.length}</span>
        <ChevronDown size={16} aria-hidden="true" />
      </summary>
      <div className="home-service-details">
        <p>
          {tr(
            'ui.available_work_is_shown_below_expand_each_service_s_availability_here_missing_data_does_not_mean_an_empty_project',
          )}
        </p>
        <ul>
          {services.map((service) => (
            <li key={service.label}>
              <span>
                {labelText(service.label)}:{' '}
                {service.error instanceof ApiError && [404, 501].includes(service.error.status)
                  ? tr('ui.unavailable_on_this_server')
                  : tr('ui.unable_to_load_data_173')}
              </span>
              <button onClick={service.retry}>
                {tr('ui.try_again')}
                <span className="sr-only"> — {labelText(service.label)}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </details>
  )
}
