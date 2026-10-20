const test = require("node:test")
const assert = require("node:assert/strict")
const P = require("../plugin/core/Providers.js")
const Apps = require("../plugin/core/AppsProvider.js")
const Web = require("../plugin/core/WebSearchProvider.js")

function listProvider(method, value) {
  return toy('mixed', [], { [method]: () => value })
}
const readList = (reg, method) => method === 'actionsFor'
  ? P.actionsFor(reg, { id: 'mixed:one', provider: 'mixed' })
  : P[method](reg, 'query')

for (const method of ['candidates', 'answers', 'fallbacks', 'filters', 'actionsFor']) {
  test(method + ' contains malformed rows, retains valid siblings, and bounds redacted diagnostics', () => {
    const cycle = {}; cycle.self = cycle
    const getter = { id: 'private-id', title: 'private-title' }
    Object.defineProperty(getter, 'data', { enumerable: true, get() { throw new Error('secret-value') } })
    const rows = [
      { id: 'first', title: 'First', data: { nested: ['safe'] } },
      null, false, 'secret-value', [], {}, { id: '', title: 'secret-value' },
      { id: 'cyclic', title: 'secret-value', data: cycle },
      { id: 'nan', title: 'secret-value', data: NaN },
      { id: 'infinity', title: 'secret-value', data: [Infinity] }, getter,
      { id: 'last', title: 'Last' }
    ]
    const reg = P.createRegistry()
    P.register(reg, listProvider(method, rows))
    const result = readList(reg, method)
    assert.deepEqual(result.map(r => r.id), method === 'filters' ? ['@mixed:first', '@mixed:last'] : ['first', 'last'])
    assert.equal(reg.errors.length, 10)
    for (const diagnostic of reg.errors) {
      assert.equal(diagnostic.provider, 'mixed')
      assert.equal(diagnostic.during, method)
      assert.equal(typeof diagnostic.row, 'number')
      assert.equal(typeof diagnostic.error, 'string')
    }
    assert.doesNotMatch(JSON.stringify(reg.errors), /secret-value|private-id|private-title|cyclic|infinity/)
    for (let i = 0; i < 8; i++) readList(reg, method)
    assert.equal(reg.errors.length, 50)
  })

  test(method + ' rejects invalid containers without re-invoking the provider', () => {
    for (const container of [null, undefined, {}, { length: 1, 0: { id: 'fake', title: 'Fake' } }, 'secret-value', 1]) {
      const reg = P.createRegistry()
      let calls = 0
      P.register(reg, toy('mixed', [], { [method]: () => { calls++; return container } }))
      assert.deepEqual(readList(reg, method), [])
      assert.equal(calls, 1)
      assert.equal(reg.errors.length, 1)
      assert.equal(reg.errors[0].provider, 'mixed')
      assert.equal(reg.errors[0].during, method)
      assert.doesNotMatch(JSON.stringify(reg.errors), /secret-value|fake/)
    }
  })

  test(method + ' clones rows without altering provider-owned data', () => {
    const row = { id: 'first', title: 'First', data: { nested: ['safe'] }, rootSearch: { when: 'empty', extra: true } }
    const reg = P.createRegistry()
    P.register(reg, listProvider(method, [row]))
    const first = readList(reg, method)[0]
    if (method !== 'filters') {
      first.data.nested[0] = 'mutation'
      first.rootSearch.when = 'searching'
    }
    first.title = 'Changed'
    const second = readList(reg, method)[0]
    assert.equal(second.title, 'First')
    assert.deepEqual(row, { id: 'first', title: 'First', data: { nested: ['safe'] }, rootSearch: { when: 'empty', extra: true } })
    if (method !== 'filters') {
      assert.deepEqual(second.data, { nested: ['safe'] })
      assert.deepEqual(second.rootSearch, { when: 'empty', extra: true })
    }
    assert.deepEqual(reg.errors, [])
  })
}

const toy = (id, rows, extra) => Object.assign({
  id,
  candidates: () => rows.map((title) => ({ id: id + ":" + title, title })),
  actionsFor: () => [{ id: "open", title: "Open " + id }],
  perform: (c, action) => (action === "open" ? { close: true, visit: true } : undefined)
}, extra || {})

test('actions require nonempty string IDs and titles, preserve valid formats, and isolate the input candidate', () => {
  const candidate = { id: 'mixed:one', provider: 'mixed', data: { value: 'safe' } }
  const action = { id: 'copy-id', title: 'Copy Desktop ID', shortcut: 'Ctrl Shift C', section: 'copy', data: { value: 'safe' } }
  const reg = P.createRegistry()
  let calls = 0
  P.register(reg, toy('mixed', [], { actionsFor: c => {
    calls++
    c.data.value = 'provider mutation'
    return [{ id: 42, title: 'Number' }, { id: 'missing' }, { id: 'empty', title: '' },
      { id: 'spaces', title: '  ' }, { id: ' ', title: 'Blank ID' }, { id: 'typed', title: 3 }, action]
  } }))
  assert.deepEqual(P.actionsFor(reg, candidate), [action])
  assert.equal(calls, 1)
  assert.deepEqual(candidate, { id: 'mixed:one', provider: 'mixed', data: { value: 'safe' } })
  assert.equal(reg.errors.length, 6)
  assert.ok(reg.errors.every(e => e.provider === 'mixed' && e.during === 'actionsFor'))
})

test('actionsFor safely returns empty for absent candidates, missing providers, and empty provider actions', () => {
  const reg = P.createRegistry()
  P.register(reg, toy('mixed', [], { actionsFor: () => [] }))
  for (const candidate of [null, undefined, {}, { provider: 'missing' }, { provider: 'mixed', id: 'mixed:one' }]) {
    assert.deepEqual(P.actionsFor(reg, candidate), [])
  }
  assert.deepEqual(reg.errors, [])
})

test('action discovery failures are attributed once without revealing the thrown payload', () => {
  const reg = P.createRegistry()
  let calls = 0
  P.register(reg, toy('mixed', [], { actionsFor: () => { calls++; throw new Error('secret-credential') } }))
  assert.deepEqual(P.actionsFor(reg, { provider: 'mixed', id: 'mixed:one' }), [])
  assert.equal(calls, 1)
  assert.deepEqual(reg.errors, [{ provider: 'mixed', during: 'actionsFor', error: 'Provider invocation failed' }])
})

for (const method of ['candidates', 'answers', 'fallbacks']) {
  test(method + ' defaults rootSearch safely while preserving explicit visibility and nested payloads', () => {
    const visibility = [undefined, null, 'wrong', [], {}, { when: 'unknown', extra: true },
      { when: 'always' }, { when: 'searching' }, { when: 'empty' }]
    const rows = visibility.map((rootSearch, i) => ({ id: 'row:' + i, title: 'Row', rootSearch, data: { i } }))
    const reg = P.createRegistry()
    P.register(reg, listProvider(method, rows))
    const result = readList(reg, method)
    assert.deepEqual(result.map(r => r.rootSearch.when), [
      ...Array(6).fill(method === 'candidates' ? 'always' : 'searching'), 'always', 'searching', 'empty'
    ])
    assert.equal(result[5].rootSearch.extra, true)
    assert.deepEqual(result.map(r => r.data.i), [0, 1, 2, 3, 4, 5, 6, 7, 8])
    assert.equal(rows[0].rootSearch, undefined)
    assert.deepEqual(rows[5].rootSearch, { when: 'unknown', extra: true })
    assert.deepEqual(reg.errors, [])
  })
}

test("candidates are tagged with their provider, in registration order", () => {
  const reg = P.createRegistry()
  P.register(reg, toy("one", ["a", "b"]))
  P.register(reg, toy("two", ["c"]))
  assert.deepEqual(P.candidates(reg).map((c) => [c.id, c.provider]), [["one:a", "one"], ["one:b", "one"], ["two:c", "two"]])
})

test("registering rejects bad ids, duplicates and missing methods", () => {
  const reg = P.createRegistry()
  assert.throws(() => P.register(reg, toy("Bad Id", [])), /Invalid provider id/)
  assert.throws(() => P.register(reg, { id: "half", candidates() {} }), /lacks actionsFor/)
  P.register(reg, toy("dup", []))
  assert.throws(() => P.register(reg, toy("dup", [])), /already registered/)
})

test("a provider that throws is skipped and recorded, the others still answer", () => {
  const reg = P.createRegistry()
  P.register(reg, toy("broken", [], { candidates: () => { throw new Error("boom") } }))
  P.register(reg, toy("fine", ["x"]))
  assert.deepEqual(P.candidates(reg).map((c) => c.id), ["fine:x"])
  assert.equal(reg.errors[0].provider, "broken")
  assert.equal(reg.errors[0].during, "candidates")
  assert.equal(reg.errors[0].error.includes("boom"), false)
})

test("unregister removes a provider's rows", () => {
  const reg = P.createRegistry()
  P.register(reg, toy("one", ["a"]))
  P.unregister(reg, "one")
  assert.deepEqual(P.candidates(reg), [])
})

test("perform and actionsFor dispatch on candidate.provider", () => {
  const reg = P.createRegistry()
  P.register(reg, toy("one", ["a"]))
  const [c] = P.candidates(reg)
  assert.deepEqual(P.actionsFor(reg, c).map((a) => a.title), ["Open one"])
  assert.deepEqual(P.perform(reg, c, "open", {}), { close: true, visit: true })
  assert.equal(P.perform(reg, c, "unknown", {}), undefined)
})

test("apps provider launches and copies through injected services", () => {
  const calls = []
  const reg = P.createRegistry()
  P.register(reg, Apps.createAppsProvider({
    entries: () => [{ id: "firefox", name: "Firefox", icon: "firefox" }, { name: "no id" }],
    launch: (id, title) => calls.push(["launch", id, title]),
    copyText: (t) => calls.push(["copy", t])
  }))
  const cands = P.candidates(reg)
  assert.deepEqual(cands.map((c) => c.id), ["app:firefox"])
  assert.deepEqual(P.perform(reg, cands[0], "open", {}), { close: true, visit: true })
  assert.equal(P.perform(reg, cands[0], "copy-id", {}).hud, "Copied to Clipboard")
  assert.deepEqual(calls, [["launch", "firefox", "Firefox"], ["copy", "firefox.desktop"]])
})

test("web search offers fallbacks only, and opens the encoded url", () => {
  const opened = []
  const reg = P.createRegistry()
  P.register(reg, Web.createWebSearchProvider({ engines: () => Web.DEFAULT_ENGINES, openUrl: (u) => opened.push(u) }))
  assert.deepEqual(P.candidates(reg), [])
  const rows = P.fallbacks(reg, "a b")
  assert.deepEqual(rows.map((r) => r.title), ["Search Google", "Search DuckDuckGo"])
  assert.ok(rows.every((r) => r.fallback && r.provider === "web-search"))
  assert.deepEqual(rows.map(r => [r.id, r.url]), [
    ["fallback:0", "https://www.google.com/search?q={query}"],
    ["fallback:1", "https://duckduckgo.com/?q={query}"]
  ])
  P.perform(reg, rows[0], "open", { query: "a b" })
  assert.deepEqual(opened, ["https://www.google.com/search?q=a%20b"])
})

test("filters() collects provider dropdown entries and skips a throwing provider", () => {
  const P = require("../plugin/core/Providers.js")
  const reg = P.createRegistry()
  const base = { candidates: () => [], actionsFor: () => [], perform: () => undefined }
  P.register(reg, Object.assign({ id: "a", filters: () => [{ id: "x", title: "X" }] }, base))
  P.register(reg, Object.assign({ id: "b", filters: () => { throw new Error("no") } }, base))
  P.register(reg, Object.assign({ id: "c" }, base))
  assert.deepStrictEqual(P.filters(reg), [{ id: "@a:x", title: "X", provider: "a" }])
  assert.strictEqual(reg.errors.length, 1)
})

test("answers() generates tagged rows for the requested query", () => {
  const reg = P.createRegistry()
  P.register(reg, { id: "calc", candidates: () => [], actionsFor: () => [], perform: () => undefined,
    answers: q => q === "2+2" ? [{ id: "calc:answer", title: "4" }] : [] })
  const rows = P.answers(reg, "2+2")
  assert.strictEqual(rows[0].answer, true)
  assert.strictEqual(rows[0].provider, "calc")
  assert.deepStrictEqual(P.answers(reg, "firefox"), [])
  assert.strictEqual(rows[0].id, "calc:answer")
  assert.strictEqual(rows[0].title, "4")
})
