import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import { createServer } from 'vite'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => {
  await server.close()
})

const { createLatestTeamReliefWorkLoader } = await server.ssrLoadModule(
  '/src/components/bullpen/board/useTeamReliefWork.js',
)

const deferred = () => {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

test('one selected team produces one relief-work request', async () => {
  const calls = []
  const loader = createLatestTeamReliefWorkLoader(async (teamId) => {
    calls.push(teamId)
    return { team: { team_id: teamId } }
  })

  const result = await loader.load(110)
  assert.deepEqual(calls, [110])
  assert.deepEqual(result, {
    current: true,
    data: { team: { team_id: 110 } },
    error: null,
  })
})

test('a previous-team response cannot replace the latest selected team', async () => {
  const requests = new Map()
  const calls = []
  const loader = createLatestTeamReliefWorkLoader((teamId) => {
    calls.push(teamId)
    const request = deferred()
    requests.set(teamId, request)
    return request.promise
  })

  const first = loader.load(110)
  const second = loader.load(147)
  requests.get(147).resolve({ team: { team_id: 147 } })
  assert.deepEqual(await second, {
    current: true,
    data: { team: { team_id: 147 } },
    error: null,
  })
  requests.get(110).resolve({ team: { team_id: 110 } })
  assert.deepEqual(await first, { current: false })
  assert.deepEqual(calls, [110, 147])
})

test('invalidated and failed requests remain safe', async () => {
  const request = deferred()
  const loader = createLatestTeamReliefWorkLoader(() => request.promise)
  const pending = loader.load(110)
  loader.invalidate()
  request.resolve({ team: { team_id: 110 } })
  assert.deepEqual(await pending, { current: false })

  const failed = createLatestTeamReliefWorkLoader(async () => {
    throw new Error('private network details')
  })
  assert.deepEqual(await failed.load(147), {
    current: true,
    data: null,
    error: true,
  })
})
