// Display-owned snapshots. QML supplies provider lookup; no core imports.
// A session retains exactly one generation; no timeout can expire displayed rows.
function create(providerFor) {
  var sessions = {}, refs = {}, serial = 0
  var prefix = Date.now().toString(36) + Math.random().toString(36).slice(2)
  function token() { return prefix + '-' + (++serial).toString(36) }
  function copy(value) { return JSON.parse(JSON.stringify(value)) }
  function open() {
    if (Object.keys(sessions).length >= 32) throw new Error('Too many result sessions; close unused sessions')
    var id = token()
    sessions[id] = []
    return id
  }
  function release(session) {
    if (!Object.prototype.hasOwnProperty.call(sessions, session)) throw new Error('Unknown result session')
    sessions[session].forEach(function(ref) { delete refs[ref] })
    sessions[session] = []
  }
  function replace(session, sections, query) {
    if (!Object.prototype.hasOwnProperty.call(sessions, session)) throw new Error('Unknown result session')
    // Prepare fully before expiring the previous displayed generation.
    var display = copy(sections), pending = {}
    display.forEach(function(section) {
      section.rows.forEach(function(candidate) {
        var ref = token()
        pending[ref] = { candidate: copy(candidate), query: String(query || ''), provider: providerFor(candidate.provider) }
        candidate.ref = ref
      })
    })
    release(session)
    for (var ref in pending) { refs[ref] = pending[ref]; sessions[session].push(ref) }
    return display
  }
  function resolve(ref) {
    var entry = refs[ref]
    if (!entry) throw new Error('Result expired; refresh the displayed results')
    if (!entry.provider || providerFor(entry.candidate.provider) !== entry.provider)
      throw new Error('Result provider is no longer available')
    return { candidate: copy(entry.candidate), query: entry.query }
  }
  function close(session) {
    if (!Object.prototype.hasOwnProperty.call(sessions, session)) return
    release(session)
    delete sessions[session]
  }
  return { open: open, replace: replace, resolve: resolve, close: close }
}
if (typeof module !== 'undefined') module.exports = { create: create }
