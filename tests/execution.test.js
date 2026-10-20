const test = require('node:test')
const assert = require('node:assert/strict')
const Execution = require('../plugin/core/Execution.js')

function fixture(overrides = {}) {
  const candidate = { id: 'toy:one', provider: 'toy', title: 'One', data: { value: 'original' } }
  const calls = [], visits = [], generic = []
  const deps = Object.assign({
    resolve: () => ({ candidate, query: 'original query' }),
    actions: () => [{ id: 'run', title: 'Run' }],
    perform: (c, a, ctx) => { calls.push({ c, a, ctx }); return { close: true, visit: true } },
    generic: (c, a) => { generic.push(a); return { toast: { style: 'success', title: a } } },
    visit: (id, query) => visits.push([id, query])
  }, overrides)
  return { api: Execution.create(deps), candidate, calls, visits, generic, deps }
}
const target = { ref: 'row-1' }

test('confirmation is single-use and changing arguments or action requires confirmation again', () => {
  const seen = []
  const f = fixture({ perform: (c, a, ctx) => {
    seen.push([a, ctx.arguments, ctx.confirmed])
    return ctx.confirmed ? { visit: true, hud: 'Done' } : { prompt: { kind: 'confirmation', title: 'Run?' } }
  } })
  let p = f.api.execute({ target, arguments: ['first'] })
  assert.equal(f.visits.length, 0)
  p = f.api.execute({ target, arguments: ['changed'], continuation: p.continuation })
  p = f.api.execute({ target, action: 'delete', arguments: ['changed'], continuation: p.continuation })
  assert.deepEqual(f.api.execute({ target, action: 'delete', arguments: ['changed'], continuation: p.continuation }), { hud: 'Done' })
  assert.deepEqual(seen, [['run', ['first'], false], ['run', ['changed'], false], ['delete', ['changed'], false], ['delete', ['changed'], true]])
  assert.equal(f.visits.length, 1)
  assert.throws(() => f.api.execute({ target, arguments: ['changed'], continuation: p.continuation }), /continuation/i)
})

test('argument prompts from providers do not grant confirmation', () => {
  const confirmed = []
  const f = fixture({ perform: (c, a, ctx) => {
    confirmed.push(ctx.confirmed)
    return confirmed.length === 1 ? { prompt: { kind: 'arguments', title: 'More' } } : {}
  } })
  const p = f.api.execute({ target, arguments: [] })
  f.api.execute({ target, arguments: ['value'], continuation: p.continuation })
  assert.deepEqual(confirmed, [false, false])
})

test('cancel and clear invalidate tokens; stale refs and unregistered stored providers never dispatch', () => {
  for (const stored of [false, true]) {
    const f = fixture({ perform: () => ({ prompt: { kind: 'confirmation', title: 'Run?' } }) })
    const t = stored ? { id: 'toy:one' } : target
    const p = f.api.execute({ target: t, arguments: [] })
    f.api.cancel(p.continuation)
    assert.throws(() => f.api.execute({ target: t, continuation: p.continuation }), /continuation/i)
    const q = f.api.execute({ target: t, arguments: [] })
    const r = f.api.execute({ target: t, arguments: [] })
    f.api.clear()
    for (const token of [q.continuation, r.continuation]) assert.throws(() => f.api.execute({ target: t, continuation: token }), /continuation/i)
    const s = f.api.execute({ target: t, arguments: [] })
    f.deps.resolve = () => { throw new Error('Stale ref or missing provider') }
    assert.throws(() => f.api.execute({ target: t, arguments: [], continuation: s.continuation }), /Stale ref/)
    assert.throws(() => f.api.execute({ target: t, arguments: [], continuation: s.continuation }), /continuation/i)
  }
})

test('provider mutation cannot change nested candidates, arguments, or pending payloads', () => {
  const received = []
  const f = fixture({
    actions: c => { c.data.value = 'actions mutation'; return [{ id: 'run', title: 'Run' }] },
    perform: (c, a, ctx) => {
      received.push(c.data.value)
      c.data.value = 'perform mutation'
      ctx.arguments[0] = 'mutation'
      return ctx.confirmed ? {} : { prompt: { kind: 'confirmation', title: 'Run?' } }
    }
  })
  f.api.actions(target)
  const args = ['safe']
  const p = f.api.execute({ target, arguments: args })
  assert.equal(f.candidate.data.value, 'original')
  assert.deepEqual(args, ['safe'])
  assert.deepEqual(p.arguments, ['safe'])
  p.arguments[0] = 'public mutation'
  p.candidate.data.value = 'public mutation'
  f.api.execute({ target, arguments: ['safe'], continuation: p.continuation })
  assert.deepEqual(received, ['original', 'original'])
})

test('known generic actions bypass script arguments but still dispatch provider first', () => {
  for (const providerHandles of [false, true]) {
    const order = []
    const f = fixture({
      isGeneric: action => action === 'favorite-add',
      perform: (c, action, ctx) => {
        order.push(['provider', action, ctx.arguments])
        return providerHandles ? { hud: 'Provider handled' } : undefined
      },
      generic: (c, action) => { order.push(['generic', action]); return { hud: 'Generic handled' } }
    })
    f.candidate.provider = 'scripts'
    f.candidate.arguments = [{ placeholder: 'Required' }]
    assert.deepEqual(f.api.execute({ target, action: 'favorite-add', arguments: [] }),
      { hud: providerHandles ? 'Provider handled' : 'Generic handled' })
    assert.deepEqual(order, providerHandles ? [['provider', 'favorite-add', []]]
      : [['provider', 'favorite-add', []], ['generic', 'favorite-add']])
    assert.equal(f.api.execute({ target, action: 'run', arguments: [] }).prompt.kind, 'arguments')
    assert.equal(f.api.execute({ target, arguments: [] }).prompt.kind, 'arguments')
    const p = f.api.execute({ target, action: 'run', arguments: [] })
    assert.equal(f.api.execute({ target, action: 'favorite-add', arguments: [], continuation: p.continuation }).prompt, undefined)
  }
  const f = fixture()
  f.candidate.arguments = [{ placeholder: 'Required' }]
  assert.equal(f.api.execute({ target, action: 'favorite-add', arguments: [] }).prompt.kind, 'arguments')
  assert.equal(f.calls.length, 0)
})

test('only explicit undefined falls through to generic; primary without an action never does', () => {
  const f = fixture({ perform: () => undefined })
  assert.throws(() => f.api.execute({ target, arguments: [] }), /may already have occurred/)
  assert.equal(f.generic.length, 0)
  assert.deepEqual(f.api.execute({ target, action: 'favorite-add', arguments: [] }), { toast: { style: 'success', title: 'favorite-add' } })
  assert.deepEqual(f.generic, ['favorite-add'])
  f.deps.actions = () => []
  assert.throws(() => f.api.execute({ target, arguments: [] }), /primary action/)
  assert.equal(f.generic.length, 1)
  f.deps.generic = () => { throw new Error('Unknown action') }
  assert.throws(() => f.api.execute({ target, action: 'unknown', arguments: [] }), /Unknown action.*may already have occurred/)
})

test('exceptions consume confirmations before dispatch with no retries or generic fallback', () => {
  const f = fixture()
  f.deps.perform = (c, a, ctx) => {
    f.calls.push(ctx.confirmed)
    if (ctx.confirmed) throw new Error('after launch')
    return { prompt: { kind: 'confirmation', title: 'Run?' } }
  }
  const p = f.api.execute({ target, arguments: [] })
  assert.throws(() => f.api.execute({ target, arguments: [], continuation: p.continuation }), /after launch.*may already have occurred/)
  assert.throws(() => f.api.execute({ target, arguments: [], continuation: p.continuation }), /continuation/i)
  assert.deepEqual(f.calls, [false, true])
  assert.deepEqual(f.generic, [])
  assert.deepEqual(f.visits, [])
})

test('continuations cannot authorize a different target or a changed provider identity', () => {
  for (const change of ['target', 'provider', 'id']) {
    const f = fixture({ perform: () => ({ prompt: { kind: 'confirmation', title: 'Run?' } }) })
    const p = f.api.execute({ target, arguments: [] })
    let nextTarget = target
    if (change === 'target') nextTarget = { ref: 'different-row' }
    else f.candidate[change] = 'different'
    assert.throws(() => f.api.execute({ target: nextTarget, arguments: [], continuation: p.continuation }), /target|provider|identity/i)
    assert.throws(() => f.api.execute({ target, arguments: [], continuation: p.continuation }), /continuation/i)
    assert.deepEqual(f.visits, [])
  }
})

test('malformed requests fail before provider dispatch', () => {
  for (const patch of [{ arguments: {} }, { arguments: [42] }, { arguments: [NaN] }, { action: 3 }, { target: {} }, { target: { ref: 'a', id: 'b' } }]) {
    const f = fixture()
    assert.throws(() => f.api.execute({ target, arguments: [], ...patch }), Error)
    assert.equal(f.calls.length, 0)
    assert.equal(f.visits.length, 0)
  }
})

const cycle = {}; cycle.self = cycle
for (const [name, value] of Object.entries({
  null: null, boolean: false, array: [], number: 1, string: 'bad',
  close: { close: 'yes' }, visit: { visit: 1 }, settings: { settings: {} }, hud: { hud: 42 },
  push: { push: [] }, pushNull: { push: null },
  toast: { toast: { style: 'info', title: 'No' } }, toastTitle: { toast: { style: 'success', title: 1 } },
  toastActions: { toast: { style: 'failure', title: 'No', actions: [{ title: 'Copy', copy: 1 }] } },
  toastActionMissing: { toast: { style: 'success', title: 'OK', actions: [{ title: 'Nothing' }] } },
  prompt: { prompt: { kind: 'other' } }, promptNull: { prompt: null }, promptTitle: { prompt: { kind: 'confirmation', title: 2 } },
  promptClose: { prompt: { kind: 'confirmation', title: '?' }, close: false },
  promptVisit: { prompt: { kind: 'arguments', title: '?' }, visit: false },
  nan: { visit: true, extra: NaN }, infinity: { extra: Infinity }, cyclic: { extra: cycle },
  undefinedField: { extra: undefined }, functionField: { extra: () => {} }, bigint: { extra: 1n },
  date: { extra: new Date() }, sparseArray: { extra: Array(2) }, promise: Promise.resolve({})
})) {
  test('invalid outcome is rejected without visits or retry: ' + name, () => {
    let count = 0
    const f = fixture({ perform: () => { count++; return value } })
    assert.throws(() => f.api.execute({ target, arguments: [] }), /may already have occurred/)
    assert.equal(count, 1)
    assert.deepEqual(f.generic, [])
    assert.deepEqual(f.visits, [])
  })
}

test('visit is consumed without mutating provider outcomes, including false and generic visits', () => {
  for (const viaGeneric of [false, true]) {
    for (const visit of [false, true]) {
      const outcome = { visit, hud: 'Done' }
      const f = fixture({ perform: () => viaGeneric ? undefined : outcome, generic: () => outcome })
      assert.deepEqual(f.api.execute({ target, action: 'favorite-add', arguments: [] }), { hud: 'Done' })
      assert.deepEqual(outcome, { visit, hud: 'Done' })
      assert.deepEqual(f.visits, visit ? [['toy:one', 'original query']] : [])
    }
  }
})

test('valid JSON and presenter fields are retained without sharing provider objects', () => {
  const outcome = { close: true, visit: true, settings: true, hud: 'Done', push: { kind: 'view', nested: [null, 1] },
    toast: { style: 'success', title: 'OK', actions: [{ title: 'Copy', copy: 'text' }, { title: 'Open', open: 'https://example.org' }] }, extra: { safe: true } }
  const f = fixture({ perform: () => outcome })
  const result = f.api.execute({ target, arguments: [] })
  const expected = { ...outcome }
  delete expected.visit
  assert.deepEqual(result, expected)
  assert.equal(outcome.visit, true)
  result.push.nested[1] = 2
  assert.equal(outcome.push.nested[1], 1)
  assert.equal(f.visits.length, 1)
})

test('generic outcomes are also validated before visits', () => {
  const f = fixture({ perform: () => undefined, generic: () => ({ visit: true, hud: NaN }) })
  assert.throws(() => f.api.execute({ target, action: 'generic', arguments: [] }), /may already have occurred/)
  assert.deepEqual(f.visits, [])
})

test('required arguments prompt before dispatch, then execute once against the private snapshot', () => {
  const f = fixture()
  f.candidate.arguments = [{ placeholder: 'Name' }, { optional: true }]
  const p = f.api.execute({ target, arguments: [] })
  assert.equal(p.prompt.kind, 'arguments')
  assert.equal(typeof p.prompt.title, 'string')
  assert.deepEqual(p.arguments, [])
  assert.equal(f.calls.length, 0)
  f.candidate.data.value = 'live replacement'
  p.candidate.data.value = 'public mutation'
  f.deps.resolve = () => ({ candidate: { id: 'toy:one', provider: 'toy', data: { value: 'new payload' } }, query: 'new query' })
  f.api.execute({ target, arguments: ['Ada'], continuation: p.continuation })
  assert.equal(f.calls.length, 1)
  assert.equal(f.calls[0].c.data.value, 'original')
  assert.deepEqual(f.calls[0].ctx, { query: 'original query', arguments: ['Ada'], confirmed: false })
  assert.deepEqual(f.visits, [['toy:one', 'original query']])
  assert.throws(() => f.api.execute({ target, arguments: ['Ada'], continuation: p.continuation }), /continuation/i)
})

test('primary uses the first provider action; explicit actions are preserved; valid visits occur once', () => {
  const f = fixture()
  assert.deepEqual(f.api.actions(target), [{ id: 'run', title: 'Run' }])
  assert.deepEqual(f.api.execute({ target, arguments: [] }), { close: true })
  f.api.execute({ target: { id: 'toy:one' }, action: '', arguments: [] })
  f.api.execute({ target, action: 'copy-id', arguments: [] })
  assert.deepEqual(f.calls.map(x => x.a), ['run', 'run', 'copy-id'])
  assert.deepEqual(f.visits, Array(3).fill(['toy:one', 'original query']))
})
