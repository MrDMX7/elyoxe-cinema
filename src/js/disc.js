/* discounts: a pure mirror of discounts.py compute(). tests/test_parity.py runs the block between
   disc:begin and disc:end in node against Python for every branch. */
/* disc:begin — a pure mirror of discounts.py compute(); tests/test_parity.py runs this block in node */
function discRule(rules, chain, c) { return rules && rules[chain] && rules[chain][c] || null; }
function discState(r, today) {
  if (!r) return "unchecked";
  if (r.status === "none_found") return "none_found";
  if (r.valid_until && String(r.valid_until) < today) return "expired";
  return r.type === "percent" || r.type === "bogo" || r.type === "fixed" ? "ok" : "none_found";
}
function discCovers(r, hall, hk, cin) {
  var names = [hall, hk].filter(function (h) { return h; }), ex = r.excluded_halls || r.halls_excluded || [], inc = r.included_halls;
  var any = function (list) { return names.some(function (h) { return list.indexOf(h) >= 0; }); };
  if (any(ex)) return false;
  if (inc != null && !any(inc)) return false;
  if (r.included_cinemas != null && r.included_cinemas.indexOf(cin) < 0) return false;
  return true;
}
function discR2(x) { return Math.round(x * 100) / 100; }
function discPrice(r, aed) {
  if (r.type === "bogo") return discR2(aed / 2);
  if (r.type === "fixed") return discR2(Math.min(aed, +r.value || 0));
  return discR2(aed * (1 - (+r.value || 0) / 100));
}
// hk: a halls.yaml key, or the slices' «chain|key» (the key is after the bar)
function discAfter(rules, today, aed, chain, hall, hk, cin, c) {
  var r = discRule(rules, chain, c), st = discState(r, today);
  if (hk && hk.indexOf("|") >= 0) hk = hk.slice(hk.indexOf("|") + 1);
  if (st !== "ok") return { a: null, st: st, r: r };
  if (!discCovers(r, hall, hk, cin)) return { a: null, st: "excluded", r: r };
  return { a: discPrice(r, aed), st: "ok", r: r };
}
// what a paid price needs said next to it: BOGO is per person and only with 2 tickets
function discPayNote(r, strings) { return r && r.type === "bogo" ? strings.per_person : ""; }
/* disc:end */
