import { useCallback, useEffect, useState } from 'react'
import type {
  DeviceJob,
  GraphitiEpisodeEnvelope,
  ProjectDevice,
  RepositoryFile,
  RepositoryIndex,
  WorkspaceModule,
  WorkspaceSnapshot,
  WorkspaceTaskStatus,
} from '../types'

const apiRoot = () => (import.meta.env.VITE_API_URL || 'https://app-production-cc16.up.railway.app').replace(/\/$/, '')

type WorkspaceRefreshOptions = { indexRepository?: boolean }

type DevicePairing = { pairing_token: string; expires_at: string; name_hint: string }

export function useWorkspace() {
  const [workspace, setWorkspace] = useState<WorkspaceSnapshot>()
  const [repository, setRepository] = useState<RepositoryIndex>()
  const [files, setFiles] = useState<RepositoryFile[]>([])
  const [devices, setDevices] = useState<ProjectDevice[]>([])
  const [deviceJobs, setDeviceJobs] = useState<DeviceJob[]>([])
  const [graphitiEpisodes, setGraphitiEpisodes] = useState<GraphitiEpisodeEnvelope[]>([])
  const [pairing, setPairing] = useState<DevicePairing>()
  const [selectedModuleId, setSelectedModuleId] = useState<string>()
  const [loading, setLoading] = useState(true)
  const [indexing, setIndexing] = useState(false)
  const [error, setError] = useState<string>()

  const refresh = useCallback(async ({ indexRepository = false }: WorkspaceRefreshOptions = {}) => {
    setLoading(true)
    try {
      const projectsResponse = await fetch(`${apiRoot()}/v1/projects`, { credentials: 'include' })
      if (!projectsResponse.ok) throw new Error('Could not load projects')
      const projects = await projectsResponse.json() as Array<{ id: string }>
      const project = projects[0]
      if (!project) throw new Error('No workspace project is available')

      if (indexRepository) {
        setIndexing(true)
        const response = await fetch(`${apiRoot()}/v1/projects/${project.id}/index`, { method: 'POST', credentials: 'include' })
        if (!response.ok) throw new Error('Could not refresh the Git project map')
      }

      const [workspaceResponse, repositoryResponse, filesResponse, devicesResponse, episodesResponse, jobsResponse] = await Promise.all([
        fetch(`${apiRoot()}/v1/projects/${project.id}/workspace`, { credentials: 'include' }),
        fetch(`${apiRoot()}/v1/projects/${project.id}/repository`, { credentials: 'include' }),
        fetch(`${apiRoot()}/v1/projects/${project.id}/files`, { credentials: 'include' }),
        fetch(`${apiRoot()}/v1/projects/${project.id}/devices`, { credentials: 'include' }),
        fetch(`${apiRoot()}/v1/projects/${project.id}/graphiti/episodes`, { credentials: 'include' }),
        fetch(`${apiRoot()}/v1/projects/${project.id}/devices/jobs`, { credentials: 'include' }),
      ])
      if (!workspaceResponse.ok) throw new Error('Could not load workspace')
      const snapshot = await workspaceResponse.json() as WorkspaceSnapshot
      setWorkspace(snapshot)
      setSelectedModuleId((current) => current && snapshot.modules.some((module) => module.id === current) ? current : snapshot.modules[0]?.id)
      setRepository(repositoryResponse.ok ? await repositoryResponse.json() as RepositoryIndex : undefined)
      setFiles(filesResponse.ok ? await filesResponse.json() as RepositoryFile[] : [])
      setDevices(devicesResponse.ok ? await devicesResponse.json() as ProjectDevice[] : [])
      setGraphitiEpisodes(episodesResponse.ok ? await episodesResponse.json() as GraphitiEpisodeEnvelope[] : [])
      setDeviceJobs(jobsResponse.ok ? await jobsResponse.json() as DeviceJob[] : [])
      setError(undefined)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load workspace')
    } finally {
      setIndexing(false)
      setLoading(false)
    }
  }, [])

  useEffect(() => { void refresh({ indexRepository: true }) }, [refresh])

  const selectedModule = workspace?.modules.find((module) => module.id === selectedModuleId)
  const indexRepository = useCallback(async () => { await refresh({ indexRepository: true }) }, [refresh])

  const createDevicePairing = useCallback(async (nameHint = 'Local Agent Room Runtime') => {
    if (!workspace) throw new Error('Workspace is not ready')
    const response = await fetch(`${apiRoot()}/v1/projects/${workspace.project.id}/devices/pair`, {
      method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name_hint: nameHint }),
    })
    if (!response.ok) throw new Error('Could not create a device pairing token')
    const nextPairing = await response.json() as DevicePairing
    setPairing(nextPairing)
    return nextPairing
  }, [workspace])

  const createDeviceJob = useCallback(async (deviceId: string, type: DeviceJob['type'], payload: Record<string, unknown> = {}) => {
    if (!workspace) throw new Error('Workspace is not ready')
    const response = await fetch(`${apiRoot()}/v1/projects/${workspace.project.id}/devices/jobs`, {
      method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ device_id: deviceId, type, payload }),
    })
    if (!response.ok) throw new Error('Could not create local semantic request')
    const job = await response.json() as DeviceJob
    await refresh()
    return job
  }, [refresh, workspace])

  const approveDeviceJob = useCallback(async (jobId: string, approved: boolean) => {
    if (!workspace) throw new Error('Workspace is not ready')
    const response = await fetch(`${apiRoot()}/v1/projects/${workspace.project.id}/devices/jobs/${jobId}/approval`, {
      method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approved }),
    })
    if (!response.ok) throw new Error('Could not approve local semantic request')
    await refresh()
  }, [refresh, workspace])

  const createNote = useCallback(async (module: WorkspaceModule, title: string, content: string, sourceRunId?: string) => {
    if (!workspace) return
    const response = await fetch(`${apiRoot()}/v1/projects/${workspace.project.id}/notes`, {
      method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ module_id: module.id, title, content, source_run_id: sourceRunId }),
    })
    if (!response.ok) throw new Error('Could not create note')
    await refresh()
  }, [refresh, workspace])

  const createTask = useCallback(async (module: WorkspaceModule, title: string, description: string, sourceRunId?: string, acceptanceCriteria: string[] = []) => {
    if (!workspace) return
    const response = await fetch(`${apiRoot()}/v1/projects/${workspace.project.id}/tasks`, {
      method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ module_id: module.id, title, description, source_run_id: sourceRunId, acceptance_criteria: acceptanceCriteria }),
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

  return {
    workspace, repository, files, devices, deviceJobs, graphitiEpisodes, pairing, selectedModule, selectedModuleId, setSelectedModuleId,
    loading, indexing, error, refresh, indexRepository, createDevicePairing, createDeviceJob, approveDeviceJob, createNote, createTask, updateTaskStatus,
  }
}
