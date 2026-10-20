const test = require('node:test')
const assert = require('node:assert/strict')
const Results = require('../plugin/core/Results.js')

test('displayed data survives provider mutation and independent searches', () => {
  const provider = {}
  const results = Results.create(() => provider)
  const a = results.open(), b = results.open()
  const candidate = {id:'calc:history-0', provider:'calc', data:{answer:'4'}}
  const sections = [{id:'answers', rows:[candidate]}]
  const display = results.replace(a, sections, '2+2')
  candidate.data.answer = '9'
  results.replace(b, [{id:'answers', rows:[]}], '3+3')
  const ref = display[0].rows[0].ref
  assert.equal(results.resolve(ref).candidate.data.answer, '4')
  assert.equal(results.resolve(ref).query, '2+2')
  results.resolve(ref).candidate.data.answer = 'changed'
  assert.equal(results.resolve(ref).candidate.data.answer, '4')
  results.replace(a, [], '')
  assert.throws(() => results.resolve(ref), /expired/i)
})

test('close expires refs immediately and a replacement provider cannot revive them', () => {
  let provider = {}
  const results = Results.create(() => provider)
  const session = results.open()
  const sections = [{id:'answers', rows:[{id:'calc:answer', provider:'calc'}]}]
  const ref = results.replace(session, sections, '2+2')[0].rows[0].ref
  provider = null
  assert.throws(() => results.resolve(ref), /provider/i)
  provider = {}
  assert.throws(() => results.resolve(ref), /provider/i)
  const next = results.replace(session, sections, '3+3')[0].rows[0].ref
  results.close(session)
  results.close(session)
  assert.throws(() => results.resolve(next), /expired/i)
  assert.throws(() => results.replace(session, [], ''), /session/i)
})

test('duplicate provider IDs still get distinct row refs and failed replacement preserves display', () => {
  const provider = {}
  const results = Results.create(() => provider)
  const session = results.open()
  const rows = [{id:'p:same', provider:'p', data:1}, {id:'p:same', provider:'p', data:2}]
  const display = results.replace(session, [{rows}], '')[0].rows
  assert.notEqual(display[0].ref, display[1].ref)
  assert.equal(results.resolve(display[1].ref).candidate.data, 2)
  const cyclic = {}; cyclic.data = cyclic
  assert.throws(() => results.replace(session, [{rows:[cyclic]}], ''))
  assert.equal(results.resolve(display[0].ref).candidate.data, 1)
})

test('sessions require explicit disposal instead of evicting live results', () => {
  const results = Results.create(() => ({}))
  const sessions = Array.from({length:32}, () => results.open())
  assert.throws(() => results.open(), /close unused/)
  results.close(sessions[0])
  assert.equal(typeof results.open(), 'string')
})
