const test = require("node:test")
const assert = require("node:assert/strict")
const Paths = require("../plugin/core/Paths.js")

const envOf = (vars) => (name) => vars[name] || ""

test("defaults follow the XDG base directory spec", () => {
  const p = Paths.resolve(envOf({ HOME: "/home/u", XDG_RUNTIME_DIR: "/run/user/1000" }))
  assert.equal(p.config, "/home/u/.config/x-cast")
  assert.equal(p.configFile, "/home/u/.config/x-cast/config.json")
  assert.equal(p.db, "/home/u/.local/share/x-cast/db")
  assert.equal(p.extensions, "/home/u/.local/share/x-cast/extensions")
  assert.equal(p.cache, "/home/u/.cache/x-cast")
  assert.equal(p.logs, "/home/u/.local/state/x-cast/logs")
  assert.equal(p.runtime, "/run/user/1000/x-cast")
  assert.equal(p.scriptCommands, "/home/u/.config/x-cast/script-commands")
})

test("absolute XDG overrides win, relative ones are ignored", () => {
  const p = Paths.resolve(envOf({
    HOME: "/home/u/",
    XDG_CONFIG_HOME: "/cfg/",
    XDG_DATA_HOME: "relative/data",
    XDG_STATE_HOME: "/st"
  }))
  assert.equal(p.config, "/cfg/x-cast")
  assert.equal(p.data, "/home/u/.local/share/x-cast")
  assert.equal(p.state, "/st/x-cast")
})

test("missing HOME is an error", () => {
  assert.throws(() => Paths.resolve(envOf({})), /HOME is not set/)
})

test("startup creates the persistent dirs and the runtime dir", () => {
  const p = Paths.resolve(envOf({ HOME: "/h", XDG_RUNTIME_DIR: "/r" }))
  assert.deepEqual(Paths.directoriesToCreate(p), [
    "/h/.config/x-cast", "/h/.local/share/x-cast/db", "/h/.cache/x-cast",
    "/h/.local/state/x-cast/logs", "/h/.local/state/x-cast/backups", "/r/x-cast"
  ])
})
