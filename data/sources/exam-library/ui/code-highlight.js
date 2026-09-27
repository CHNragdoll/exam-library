/* Small offline highlighter for source-code blocks in 408 papers. */
(() => {
  'use strict';

  const keywords = new Set([
    'break', 'case', 'catch', 'continue', 'default', 'do', 'else', 'for',
    'goto', 'if', 'return', 'switch', 'throw', 'try', 'while', 'new', 'delete',
    'class', 'public', 'private', 'protected', 'const', 'static', 'extern',
    'volatile', 'register', 'inline', 'namespace', 'using', 'template',
    'true', 'false', 'NULL', 'nullptr'
  ]);
  const types = new Set([
    'bool', 'char', 'double', 'enum', 'float', 'int', 'long', 'short', 'signed',
    'size_t', 'struct', 'typedef', 'union', 'unsigned', 'void', 'wchar_t',
    'string', 'String', 'FILE'
  ]);
  const number = /^(?:0[xX][\da-fA-F]+|0[bB][01]+|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)(?:[uUlLfF]*)/;
  const identifier = /^[A-Za-z_][A-Za-z_0-9]*/;
  const operator = /^[+\-*\/%=&|^!<>?:~]+/;

  function highlight(code) {
    if (!code || code.dataset.examHighlighted === 'true') return;
    const source = code.textContent;
    const fragment = code.ownerDocument.createDocumentFragment();
    const token = (value, kind) => {
      const span = code.ownerDocument.createElement('span');
      span.className = `code-token code-token-${kind}`;
      span.textContent = value;
      fragment.append(span);
    };
    const plain = value => fragment.append(code.ownerDocument.createTextNode(value));
    let index = 0;
    while (index < source.length) {
      const rest = source.slice(index);
      let value, kind;
      if (rest.startsWith('//')) {
        value = rest.match(/^[^\n\r]*/)[0];
        kind = 'comment';
      } else if (rest.startsWith('/*')) {
        const end = rest.indexOf('*/', 2);
        value = end < 0 ? rest : rest.slice(0, end + 2);
        kind = 'comment';
      } else if ((rest[0] === '"' || rest[0] === "'")) {
        const quote = rest[0];
        let end = 1;
        while (end < rest.length) {
          if (rest[end] === '\\') { end += 2; continue; }
          if (rest[end] === quote) { end++; break; }
          if (rest[end] === '\n') break;
          end++;
        }
        value = rest.slice(0, end);
        kind = 'string';
      } else if (rest[0] === '#' && (!index || source.slice(0, index).endsWith('\n'))) {
        value = rest.match(/^[^\n\r]*/)[0];
        kind = 'directive';
      } else if (/\d/.test(rest[0])) {
        value = rest.match(number)?.[0];
        kind = value ? 'number' : null;
      } else if (/[A-Za-z_]/.test(rest[0])) {
        value = rest.match(identifier)[0];
        if (types.has(value)) kind = 'type';
        else if (keywords.has(value)) kind = 'keyword';
        else if (/^[A-Z][A-Z_0-9]+$/.test(value)) kind = 'constant';
        else if (/^\s*\(/.test(source.slice(index + value.length))) kind = 'function';
      } else if (operator.test(rest)) {
        value = rest.match(operator)[0];
        kind = 'operator';
      }
      if (!value) value = rest[0];
      if (kind) token(value, kind);
      else plain(value);
      index += value.length;
    }
    // A highlighted block stays selectable/copyable as exactly the source text.
    if (fragment.textContent !== source) return;
    code.replaceChildren(fragment);
    code.dataset.examHighlighted = 'true';
  }

  function apply(root = document) {
    for (const code of root.querySelectorAll('pre.code > code')) highlight(code);
  }

  window.ExamCodeHighlight = {apply};
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => apply(), {once: true});
  } else {
    apply();
  }
})();
