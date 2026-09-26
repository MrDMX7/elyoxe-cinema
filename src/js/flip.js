/* the flip board: prices and the «الحين» time are drawn digit by digit; a digit that changed turns over.
   prefers-reduced-motion: the new value just appears. */
function flipDigits(str, go) {
  if (!go || RM) return esc(str);
  return String(str).split("").map(function (ch, i) {
    return /\d/.test(ch) ? '<span class="fd" style="--i:' + i + '">' + ch + "</span>" : esc(ch);
  }).join("");
}
function flipTime(el, t) {
  var old = el.getAttribute("data-t") || "";
  if (old === t) return;
  el.setAttribute("data-t", t);
  el.setAttribute("aria-label", t);
  el.innerHTML = t.split("").map(function (ch, i) {
    return ch === ":" ? '<span class="c" aria-hidden="true">:</span>'
      : '<span class="d' + (!RM && old.charAt(i) !== ch ? " go" : "") + '" aria-hidden="true">' + esc(ch) + "</span>";
  }).join("");
}
