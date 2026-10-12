document.querySelectorAll('[data-confirm]').forEach(button => button.addEventListener('click', event => {
  if (!window.confirm(button.dataset.confirm)) event.preventDefault();
}));
document.querySelectorAll('[data-sidebar-toggle]').forEach(button => button.addEventListener('click', () => document.body.classList.toggle('menu-open')));
document.querySelectorAll('[data-sidebar-close], .sidebar a').forEach(button => button.addEventListener('click', () => document.body.classList.remove('menu-open')));
document.addEventListener('keydown', event => { if (event.key === 'Escape') document.body.classList.remove('menu-open'); });
document.querySelectorAll('[data-open-dialog]').forEach(button => button.addEventListener('click', () => {
  const dialog = document.getElementById(button.dataset.openDialog);
  if (dialog && !dialog.open) dialog.showModal();
}));
document.querySelectorAll('[data-close-dialog]').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
document.querySelectorAll('dialog[data-auto-modal][open]').forEach(dialog => { dialog.removeAttribute('open'); dialog.showModal(); });
document.querySelectorAll('[data-file-search]').forEach(input => input.addEventListener('input', () => {
  const search = input.value.toLowerCase();
  document.querySelectorAll('[data-file-name]').forEach(row => { row.hidden = !row.dataset.fileName.toLowerCase().includes(search); });
}));
document.querySelectorAll('[data-code-editor]').forEach(editor => {
  const area = editor.querySelector('textarea'), pre = editor.querySelector('.code-highlight'), numbers = editor.querySelector('.line-numbers');
  if (!area || !pre) return;
  const paint = () => {
    pre.replaceChildren();
    const source = area.value;
    const token = /("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\/\/[^\n]*|#[^\n]*|\/\*[\s\S]*?\*\/|\b(?:function|return|class|if|else|for|while|include|require|echo|def|import|from|const|let|var|true|false|null)\b|\b\d+(?:\.\d+)?\b)/g;
    let last = 0, match;
    while ((match = token.exec(source))) {
      pre.append(document.createTextNode(source.slice(last, match.index)));
      const span = document.createElement('span'); span.textContent = match[0];
      span.className = /^("|')/.test(match[0]) ? 'code-string' : /^(\/\/|\/\*|#)/.test(match[0]) ? 'code-comment' : /^\d/.test(match[0]) ? 'code-number' : 'code-keyword';
      pre.append(span); last = token.lastIndex;
    }
    pre.append(document.createTextNode(source.slice(last) + '\n'));
    numbers.textContent = source.split('\n').map((_, i) => i + 1).join('\n');
    pre.scrollTop = area.scrollTop; pre.scrollLeft = area.scrollLeft;
    numbers.style.transform = `translateY(${-area.scrollTop}px)`;
  };
  editor.classList.add('enhanced-code'); paint();
  area.addEventListener('input', paint);
  area.addEventListener('scroll', paint);
  area.addEventListener('keydown', event => {
    if (event.key === 'Tab') { event.preventDefault(); area.setRangeText('    ', area.selectionStart, area.selectionEnd, 'end'); paint(); }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); area.closest('form').requestSubmit(); }
  });
});
