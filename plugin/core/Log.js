// Log levels and line formatting (reference/05 §3.1 levels). The lines go
// to the shell's own log via console.*; `qs log` / the journal keep them.

var LEVELS = ["trace", "debug", "info", "warning", "error", "fatal"]

function levelIndex(level) {
  var i = LEVELS.indexOf(String(level || "").toLowerCase())
  return i < 0 ? LEVELS.indexOf("info") : i
}

function shouldLog(level, threshold) {
  return levelIndex(level) >= levelIndex(threshold)
}

// "[x-cast] [info] [system] message {json}". Metadata is optional and
// serialized on one line so a log stays grep-able.
function format(level, category, message, metadata) {
  var line = "[x-cast] [" + LEVELS[levelIndex(level)] + "]"
  if (category) line += " [" + category + "]"
  line += " " + String(message)
  if (metadata !== undefined && metadata !== null) {
    try { line += " " + JSON.stringify(metadata) } catch (e) { line += " {unserializable}" }
  }
  return line
}

if (typeof module !== "undefined") {
  module.exports = { LEVELS: LEVELS, levelIndex: levelIndex, shouldLog: shouldLog, format: format }
}
