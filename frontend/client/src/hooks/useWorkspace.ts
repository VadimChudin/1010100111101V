import { useCallback, useEffect, useState } from 'react'
import type { WorkspaceModule, WorkspaceSnapshot, WorkspaceTaskStatus } from '../types'

const apiRoot = () => (import.meta.env.VITE_API_URL || 'https://app-production-cc16.up.railway.app').replace(/\/$/, '')

export function useWorkspace() {
  const [workspace, setWorkspace] = useState<WorkspaceSnapshot>()
  const [selectedModuleId, setSelectedModuleId] = useState<string>()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string>()

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const projectsResponse = await fetch(`${apiRoot()}/v1/projects`, { credentials: 'include' })
      if (!projectsResponse.ok) throw new Error('Could not load projects')
      const projects = await projectsResponse.json() as Array<{ id: string }>
      const project = projects[0]
      if (!project) throw new Error('No workspace project is available')
      const workspaceResponse = await fetch(`${apiRoot()}/v1/projects/${project.id}/workspace`, { credentials: 'include' })
      if (!workspaceResponse.ok) throw new Error('Could not load workspace')
      const snapshot = await workspaceResponse.json() as WorkspaceSnapshot
      setWorkspace(snapshot)
      setSelectedModuleId((current) => current && snapshot.modules.some((module) => module.id === current) ? current : snapshot.modules[0]?.id)
      setError(undefined)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load workspace')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void refresh() }, [refresh])

  const selectedModule = workspace?.modules.find((module) => module.id === selectedModuleId)

  const createNote = useCallback(async (module: WorkspaceModule, title: string, content: string) => {
    if (!workspace) return
    const response = await fetch(`${apiRoot()}/v1/projects/${workspace.project.id}/notes`, {
      method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ module_id: module.id, title, content }),
    })
    if (!response.ok) throw new Error('Could not create note')
    await refresh()
  }, [refresh, workspace])

  const createTask = useCallback(async (module: WorkspaceModule, title: string, description: string) => {
    if (!workspace) return
    const response = await fetch(`${apiRoot()}/v1/projects/${workspace.project.id}/tasks`, {
      method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ module_id: module.id, title, description }),
    })
    if (!response.ok) throw new Error('Could not create task')
    await refresh()
  }, [refresh, workspace])

  const updateTaskStatus = useCallback(async (taskId: string, status: WorkspaceTaskStatus) => {
    if (!workspace) return
    const response = await fetch(`${apiRoot()}/v1/projects/${workspace.project.id}/tasks/${taskId}`, {
      method: 'PATCH', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }),
    })
    if (!response.ok) throw new Error('Could not update task')
    await refresh()
  }, [refresh, workspace])

  return { workspace, selectedModule, selectedModuleId, setSelectedModuleId, loading, error, refresh, createNote, createTask, updateTaskStatus }
}
