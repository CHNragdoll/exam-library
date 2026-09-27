/* Render only answer text, using the locally bundled MathJax component. */
(() => {
  'use strict';
  const ownScript = document.currentScript || [...document.scripts]
    .find(node => /\/answer-math\.js(?:[?#]|$)/.test(node.src));
  if (!ownScript?.src) return;
  const vendorUrl = new URL('vendor/mathjax-3.2.2-tex-svg-full.js', ownScript.src).href;
  let mathReady;
  let renderQueue = Promise.resolve();

  const loadMath = () => {
    if (window.MathJax?.typesetPromise) return Promise.resolve(window.MathJax);
    if (!mathReady) {
      window.MathJax = {
        startup: {typeset: false},
        tex: {
          // Current answers use \(...\); support display delimiters as well.
          // Dollar delimiters are deliberately excluded so amounts stay text.
          inlineMath: [['\\(', '\\)']], displayMath: [['\\[', '\\]']],
          // boldsymbol is needed by math3 vectors. The full component bundles
          // it locally; unsafe HTML and network-loading TeX packages stay off.
          packages: ['base', 'ams', 'newcommand', 'noundefined', 'boldsymbol']
        },
        options: {skipHtmlTags: ['script', 'noscript', 'style', 'textarea',
          'pre', 'code', 'mjx-container']}
      };
      mathReady = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = vendorUrl;
        script.onload = () => Promise.resolve(window.MathJax?.startup?.promise)
          .then(() => {
            if (!window.MathJax?.typesetPromise) throw new Error('MathJax did not initialize');
            resolve(window.MathJax);
          }, reject);
        script.onerror = () => reject(new Error('Local MathJax unavailable'));
        document.head.append(script);
      }).catch(error => { mathReady = null; throw error; });
    }
    return mathReady;
  };

  document.addEventListener('toggle', event => {
    const panel = event.target;
    if (!panel.matches?.('details.answer-panel, details.exam-answer-panel') ||
        !panel.open || panel.dataset.examMathRendered === 'true' ||
        panel.dataset.examMathRendering === 'true' ||
        !/\\(?:\(|\[)/.test(panel.textContent)) return;
    panel.dataset.examMathRendering = 'true';
    renderQueue = renderQueue.catch(() => {}).then(() => loadMath())
      .then(math => math.typesetPromise([panel]))
      .then(() => { panel.dataset.examMathRendered = 'true'; })
      .catch(() => { /* Keep the original, safely inserted answer text. */ })
      .finally(() => { delete panel.dataset.examMathRendering; });
  }, true);
})();
