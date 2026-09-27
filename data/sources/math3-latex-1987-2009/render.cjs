// Offline build only. The exported HTM needs no MathJax download or server.
const fs = require('fs');
const base = './work/render/node_modules/mathjax-full/js/';
const {mathjax} = require(base + 'mathjax.js');
const {TeX} = require(base + 'input/tex.js');
const {SVG} = require(base + 'output/svg.js');
const {liteAdaptor} = require(base + 'adaptors/liteAdaptor.js');
const {RegisterHTMLHandler} = require(base + 'handlers/html.js');
const {AllPackages} = require(base + 'input/tex/AllPackages.js');
const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);
const tex = new TeX({packages: AllPackages.filter(p => !['autoload','require'].includes(p))});
const svg = new SVG({fontCache: 'none'});
const document = mathjax.document('', {InputJax: tex, OutputJax: svg});
const inputs = JSON.parse(fs.readFileSync('work/formulas.json', 'utf8'));
const results = inputs.map(item => {
  try {
    const node = document.convert(item.tex, {display: item.display, em: 18, ex: 9, containerWidth: 720});
    const markup = adaptor.outerHTML(node);
    if (/data-mml-node="merror"/.test(markup)) throw new Error(markup.match(/data-mjx-error="([^"]*)"/)?.[1] || 'merror');
    return {...item, markup};
  } catch(e) {return {...item, error: String(e)};}
});
fs.writeFileSync('work/rendered.json', JSON.stringify(results));
fs.writeFileSync('mathjax.css', adaptor.textContent(svg.styleSheet(document)));
console.log(JSON.stringify({formulas: results.length, errors:results.filter(r=>r.error).map(({id,tex,error})=>({id,tex,error}))}));
if (results.some(r=>r.error)) process.exitCode = 1;
