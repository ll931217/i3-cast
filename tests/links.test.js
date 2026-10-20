const test = require("node:test")
const assert = require("node:assert")
const Links = require("../plugin/core/Links.js")

test("parses extension and script-command links with arguments", () => {
  const link = Links.parse("raycast://extensions/acme/My%20Tools/Say-Hello?arguments=%7B%22argument1%22%3A%22Ann%22%7D")
  assert.deepStrictEqual(link, { command: "say-hello", extension: "my-tools", arguments: { argument1: "Ann" } })
  assert.deepStrictEqual(Links.parse("raycast://script-commands/hello"), { command: "hello", extension: "", arguments: null })
})

test("other raycast links and junk are not command links", () => {
  assert.strictEqual(Links.parse("raycast://confetti"), null)
  assert.strictEqual(Links.parse("https://example.com"), null)
  assert.strictEqual(Links.parse(""), null)
})

const hello = { id: "script-commands:/s/hello.sh", title: "Say Hello", subtitle: "Demo", arguments: [{ name: "argument1", optional: false }, { name: "argument2", optional: true }] }
const other = { id: "script-commands:/t/hello.sh", title: "Say Hello", subtitle: "Other", arguments: [] }

test("resolves by title slug, preferring the matching package", () => {
  const r = Links.resolve([other, hello], { command: "say-hello", extension: "demo", arguments: { argument1: "Ann" } })
  assert.strictEqual(r.candidate, hello)
  assert.deepStrictEqual(r.arguments, ["Ann", ""])
  assert.strictEqual(r.missingArguments, false)
})

test("flags a missing required argument, accepts positional arrays, and misses unknown commands", () => {
  assert.strictEqual(Links.resolve([hello], { command: "say-hello", extension: "", arguments: null }).missingArguments, true)
  assert.deepStrictEqual(Links.resolve([hello], { command: "say-hello", extension: "", arguments: ["Bo", "x"] }).arguments, ["Bo", "x"])
  assert.strictEqual(Links.resolve([hello], { command: "nope", extension: "", arguments: null }), null)
})

test("slug drops .desktop and punctuation", () => {
  assert.strictEqual(Links.slug("Firefox Web Browser.desktop"), "firefox-web-browser")
})
