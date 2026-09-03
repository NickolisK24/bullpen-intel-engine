import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { createServer } from 'vite'

const board = readFileSync('src/components/bullpen/board/TonightsBullpenBoard.jsx', 'utf8')
const shell = readFileSync('src/components/bullpen/Bullpen.jsx', 'utf8')
const menu = readFileSync('src/components/share/EvidenceShareMenu.jsx', 'utf8')

const server = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
test.after(() => server.close())
const { createTeamShareCardLoader } = await server.ssrLoadModule(
  '/src/components/bullpen/board/TonightsBullpenBoard.jsx',
)

test('selected Team Board has one eager core request and one deferred identified request', () => {
  assert.equal((shell.match(/useFetch\(getTeams\)/g) || []).length, 1)
  assert.equal((board.match(/useFetch\(/g) || []).length, 2)
  assert.equal((board.match(/getTeamBoardCore\(selectedTeam, options\)/g) || []).length, 1)
  assert.equal((board.match(/getTeamBoardDetails\(selectedTeam, coreIdentity, options\)/g) || []).length, 1)
  assert.ok(board.includes('readTeamBoardDelivery'))
  assert.equal(board.includes('getTeamBullpenBoard'), false)
  assert.equal(board.includes('getTeamChanges'), false)
})

test('What Changed is deferred while operating disclosure is carried by core', () => {
  assert.ok(board.includes('teamBoardRead?.whatChanged'))
  assert.ok(board.includes('teamBoardRead?.operatingState'))
  assert.ok(board.includes('teamBoardRead?.sectionStatus?.what_changed'))
})

test('share-card work starts only from the explicit share-menu interaction', () => {
  assert.equal((board.match(/createTeamShareCardLoader\(selectedTeam\)/g) || []).length, 1)
  assert.ok(board.includes('loadCardModel={loadTeamCard}'))
  assert.ok(menu.includes("typeof loadCardModel !== 'function'"))
  assert.ok(menu.includes('const loaded = await loadCardModel()'))
  assert.ok(menu.includes('if (loaded) setLoadedCardModel(loaded)'))
  assert.ok(menu.includes('onClick={openMenu}'))
})

test('creating the share loader is inert and invocation preserves the artifact owner', async () => {
  const calls = []
  const artifact = { capability: 'immutable_share_artifact' }
  const model = { destinationUrl: 'https://baseballos.app/share/example' }
  const loader = createTeamShareCardLoader(
    147,
    async teamId => {
      calls.push(teamId)
      return artifact
    },
    value => {
      assert.equal(value, artifact)
      return model
    },
  )

  assert.deepEqual(calls, [])
  assert.equal(await loader(), model)
  assert.deepEqual(calls, [147])
})

test('team switches cannot render the prior team response', () => {
  assert.ok(board.includes('teamBoardV2State.loading'))
  assert.ok(board.includes('coreIdentity?.snapshot_id'))
  assert.ok(board.includes('<div key={selectedTeam}'))
})
