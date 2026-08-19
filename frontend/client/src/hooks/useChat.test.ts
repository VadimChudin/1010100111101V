import { describe, expect, it } from 'vitest'

import { normalizePlan } from './useChat'

describe('normalizePlan', () => {
  it('accepts the object-shaped plan returned by the chat API', () => {
    expect(
      normalizePlan({
        goal: 'Fix chat',
        steps: [
          {
            id: 'contract',
            title: 'Align the API contract',
            description: 'Return a plan envelope with a steps array.',
            depends_on: [],
          },
        ],
        acceptance_criteria: ['The UI renders the plan without a map error.'],
      }),
    ).toEqual([
      {
        id: 'contract',
        title: 'Align the API contract',
        description: 'Return a plan envelope with a steps array.',
        depends_on: [],
        status: 'pending',
        tool: undefined,
      },
    ])
  })

  it('returns an empty array for an invalid plan payload', () => {
    expect(normalizePlan({} as never)).toEqual([])
  })
})
