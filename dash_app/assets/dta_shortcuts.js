/**
 * DTA page keyboard shortcuts (Phase 4).
 * Undo / redo / run when DTA controls are present; ignores typing in inputs.
 */
(function () {
  function isEditableTarget(el) {
    if (!el || !el.tagName) return false;
    var tag = el.tagName.toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return true;
    if (el.isContentEditable) return true;
    return false;
  }

  function modifierDown(e) {
    return e.ctrlKey || e.metaKey;
  }

  document.addEventListener(
    'keydown',
    function (e) {
      if (!modifierDown(e)) return;
      if (isEditableTarget(e.target)) return;

      var undo = document.getElementById('dta-undo-btn');
      var redo = document.getElementById('dta-redo-btn');
      var run = document.getElementById('dta-run-btn');
      if (!undo && !redo && !run) return;

      var key = e.key;
      if (key === 'Enter' || key === 'enter') {
        if (run && run.disabled !== true) {
          e.preventDefault();
          run.click();
        }
        return;
      }

      if (key !== 'z' && key !== 'Z') return;

      if (e.shiftKey) {
        if (redo && redo.disabled !== true) {
          e.preventDefault();
          redo.click();
        }
        return;
      }

      if (undo && undo.disabled !== true) {
        e.preventDefault();
        undo.click();
      }
    },
    true
  );
})();
