import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import { useWorkspace } from '@/app/providers/WorkspaceProvider'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { ApiError, request } from '@/lib/api/client'
import { path, projectSchema, type Project } from '../lib/api'

export function ProjectDialog({ project, onClose }: { project?: Project; onClose: () => void }) {
  const { t } = useTranslation()
  const { csrf, context, selectProject } = useWorkspace()
  const client = useQueryClient(),
    navigate = useNavigate()
  const [name, setName] = useState(project?.name ?? '')
  const [description, setDescription] = useState(project?.description ?? '')
  const [key, setKey] = useState(() => crypto.randomUUID())
  const [validation, setValidation] = useState(false)
  const mutation = useMutation({
    retry: false,
    mutationFn: async () => {
      const result = await request(project ? path(project.id) : '/api/projects', projectSchema, {
        method: project ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf ?? '' },
        body: JSON.stringify({
          name: name.trim(),
          description: description.trim(),
          idempotency_key: key,
          ...(project ? { expected_generation: project.generation } : {}),
        }),
      })
      if (
        result.organization_id !== context?.organization.id ||
        (project && result.id !== project.id)
      )
        throw new ApiError(502, 'errors.scope')
      return result
    },
    onSuccess: async (result) => {
      await client.invalidateQueries({ queryKey: ['workspace-context'] })
      await client.invalidateQueries({ queryKey: ['projects'] })
      selectProject(result.id)
      onClose()
      await navigate({ to: '/projects/$projectId', params: { projectId: result.id } })
    },
  })
  function change() {
    setKey(crypto.randomUUID())
    mutation.reset()
    setValidation(false)
  }
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !mutation.isPending) onClose()
      }}
    >
      <DialogContent
        className="project-dialog"
        closeDisabled={mutation.isPending}
        onEscapeKeyDown={(event) => {
          if (mutation.isPending) event.preventDefault()
        }}
        onPointerDownOutside={(event) => {
          if (mutation.isPending) event.preventDefault()
        }}
      >
        <DialogTitle>{t(project ? 'projects.edit' : 'projects.create')}</DialogTitle>
        <DialogDescription className="sr-only">{t('projects.emptyDescription')}</DialogDescription>
        <form
          onSubmit={(event) => {
            event.preventDefault()
            if (name.trim().length < 2 || name.trim().length > 120 || /[\n\t\r]/.test(name)) {
              setValidation(true)
              return
            }
            if (!mutation.isPending && csrf) mutation.mutate()
          }}
        >
          <label htmlFor="project-name">
            {t('projects.name')} <span aria-hidden="true">*</span>
          </label>
          <input
            id="project-name"
            required
            maxLength={120}
            value={name}
            disabled={mutation.isPending}
            aria-invalid={validation || undefined}
            aria-describedby={validation ? 'project-error' : undefined}
            onChange={(event) => {
              setName(event.target.value)
              change()
            }}
          />
          <label htmlFor="project-objective">
            {t('projects.objective')} <span className="text-muted">({t('projects.optional')})</span>
          </label>
          <textarea
            id="project-objective"
            rows={3}
            maxLength={2000}
            value={description}
            disabled={mutation.isPending}
            onChange={(event) => {
              setDescription(event.target.value)
              change()
            }}
          />
          {(validation || mutation.error) && (
            <p id="project-error" role="alert" className="project-form-error">
              {t(
                validation
                  ? 'projects.validation'
                  : mutation.error instanceof ApiError && mutation.error.status === 409
                    ? 'projects.conflict'
                    : 'projects.error',
              )}
            </p>
          )}
          <footer>
            <Button
              type="button"
              variant="secondary"
              disabled={mutation.isPending}
              onClick={onClose}
            >
              {t('projects.cancel')}
            </Button>
            <Button type="submit" disabled={mutation.isPending || !csrf}>
              {t(
                mutation.isPending
                  ? 'projects.saving'
                  : project
                    ? 'projects.save'
                    : 'projects.create',
              )}
            </Button>
          </footer>
        </form>
      </DialogContent>
    </Dialog>
  )
}
