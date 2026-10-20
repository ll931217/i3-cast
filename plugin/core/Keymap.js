// Keyboard commands for the launcher (reference/04 §2.8). Pure: QML turns a key event into
// a plain key name ("a".."z", "up", "down", "tab", "backtab"), this picks the command.
//
// mode: "emacs" (default) or "vim-motions" (general.navigationBindings).
//   emacs        Ctrl+N down, Ctrl+P up, Ctrl+K actions
//   vim-motions  Ctrl+J down, Ctrl+K up, Ctrl+H back, Ctrl+L open; Ctrl+N and Ctrl+P keep working
// Ctrl+K moves to "up" in vim mode, so the action panel moves to Ctrl+Shift+K in both modes. [D]
// Ctrl+P opens the view's dropdown when it declares one, else it is "up". [D]
// Ctrl+T focuses the toast's actions.

function resolve(mode, mods, key, hasDropdown) {
  if (!mods.ctrl || mods.alt) return ""
  var vim = mode === "vim-motions"
  if (mods.shift) return key === "k" ? "actions" : ""
  switch (key) {
    case "n": return "down"
    case "p": return hasDropdown ? "dropdown" : "up"
    case "t": return "toast"
    case "k": return vim ? "up" : "actions"
    case "j": return vim ? "down" : ""
    case "h": return vim ? "back" : ""
    case "l": return vim ? "open" : ""
  }
  return ""
}

if (typeof module !== "undefined") module.exports = { resolve: resolve }
